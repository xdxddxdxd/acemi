"""0x88 chess board, FEN handling, reversible moves, and Zobrist hashing."""

from __future__ import annotations

import random
from dataclasses import dataclass

EMPTY = 0
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = range(1, 7)
WHITE = 1
BLACK = -1

WHITE_KING_SIDE = 1
WHITE_QUEEN_SIDE = 2
BLACK_KING_SIDE = 4
BLACK_QUEEN_SIDE = 8
ALL_CASTLING_RIGHTS = 15
ROOK_RIGHT_BY_SQUARE = {
    7 * 16 + 7: WHITE_KING_SIDE,
    7 * 16: WHITE_QUEEN_SIDE,
    7: BLACK_KING_SIDE,
    0: BLACK_QUEEN_SIDE,
}

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

PIECE_TO_CHAR = {
    PAWN: "P",
    KNIGHT: "N",
    BISHOP: "B",
    ROOK: "R",
    QUEEN: "Q",
    KING: "K",
}
CHAR_TO_PIECE = {value: key for key, value in PIECE_TO_CHAR.items()}
PROMOTION_CHARS = {KNIGHT: "n", BISHOP: "b", ROOK: "r", QUEEN: "q"}
PROMOTION_TYPES = (QUEEN, ROOK, BISHOP, KNIGHT)


def is_valid_square(square: int) -> bool:
    return 0 <= square < 128 and (square & 0x88) == 0


def square_name(square: int) -> str:
    if not is_valid_square(square):
        raise ValueError(f"Invalid 0x88 square: {square}")
    file_name = chr(ord("a") + (square & 7))
    rank_name = str(8 - (square >> 4))
    return file_name + rank_name


def parse_square(name: str) -> int:
    if len(name) != 2 or name[0] not in "abcdefgh" or name[1] not in "12345678":
        raise ValueError(f"Invalid square name: {name!r}")
    return (8 - int(name[1])) * 16 + ord(name[0]) - ord("a")


@dataclass(frozen=True, slots=True)
class Move:
    """A move in 0x88 coordinates. Promotion is a piece type, not a signed piece."""

    from_square: int
    to_square: int
    promotion: int | None = None

    def uci(self) -> str:
        text = square_name(self.from_square) + square_name(self.to_square)
        if self.promotion is not None:
            text += PROMOTION_CHARS[self.promotion]
        return text


@dataclass(slots=True)
class UndoState:
    move: Move
    moving_piece: int
    captured_piece: int
    captured_square: int
    castling_rights: int
    en_passant_square: int | None
    halfmove_clock: int
    fullmove_number: int
    side_to_move: int
    zobrist_hash: int


class ZobristKeys:
    """Deterministic keys so hashes are stable across runs and Python versions."""

    def __init__(self) -> None:
        rng = random.Random(0xAC3E_2026)
        self.piece_square = [[rng.getrandbits(64) for _ in range(128)] for _ in range(12)]
        self.black_to_move = rng.getrandbits(64)
        self.castling = [rng.getrandbits(64) for _ in range(16)]
        self.en_passant_file = [rng.getrandbits(64) for _ in range(8)]


ZOBRIST = ZobristKeys()


def _piece_key_index(piece: int) -> int:
    return piece - 1 if piece > 0 else 6 + (-piece - 1)


class Board:
    """Chess position using a 128-cell 0x88 mailbox."""

    def __init__(self, fen: str = STARTING_FEN) -> None:
        self.squares = [EMPTY] * 128
        self.piece_squares: dict[int, set[int]] = {
            piece: set() for piece in range(-KING, KING + 1) if piece != EMPTY
        }
        self.king_squares = {WHITE: -1, BLACK: -1}
        self.side_to_move = WHITE
        self.castling_rights = 0
        self.en_passant_square: int | None = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.zobrist_hash = 0
        self.undo_stack: list[UndoState] = []
        self.position_hashes: list[int] = []
        self.set_fen(fen)

    @classmethod
    def from_fen(cls, fen: str) -> Board:
        return cls(fen)

    def set_fen(self, fen: str) -> None:
        fields = fen.strip().split()
        if not 4 <= len(fields) <= 6:
            raise ValueError("FEN must contain 4 to 6 fields")

        placement, active_color, castling, ep = fields[:4]
        halfmove = int(fields[4]) if len(fields) >= 5 else 0
        fullmove = int(fields[5]) if len(fields) >= 6 else 1
        if halfmove < 0 or fullmove < 1:
            raise ValueError("Invalid FEN move counters")

        ranks = placement.split("/")
        if len(ranks) != 8:
            raise ValueError("FEN piece placement must contain 8 ranks")

        squares = [EMPTY] * 128
        piece_squares = {piece: set() for piece in range(-KING, KING + 1) if piece != EMPTY}
        king_squares = {WHITE: -1, BLACK: -1}
        for row, rank_text in enumerate(ranks):
            file_index = 0
            for symbol in rank_text:
                if symbol.isdigit():
                    count = int(symbol)
                    if not 1 <= count <= 8:
                        raise ValueError("Invalid empty-square count in FEN")
                    file_index += count
                    continue
                piece_type = CHAR_TO_PIECE.get(symbol.upper())
                if piece_type is None or file_index >= 8:
                    raise ValueError(f"Invalid piece placement character: {symbol!r}")
                color = WHITE if symbol.isupper() else BLACK
                piece = color * piece_type
                square = row * 16 + file_index
                squares[square] = piece
                piece_squares[piece].add(square)
                if piece_type == KING:
                    if king_squares[color] != -1:
                        raise ValueError("FEN contains more than one king of a color")
                    king_squares[color] = square
                file_index += 1
            if file_index != 8:
                raise ValueError("Each FEN rank must describe exactly 8 squares")

        if king_squares[WHITE] == -1 or king_squares[BLACK] == -1:
            raise ValueError("FEN must contain one king of each color")
        if active_color not in ("w", "b"):
            raise ValueError("FEN active color must be 'w' or 'b'")

        castling_rights = 0
        if castling != "-":
            symbols = {
                "K": WHITE_KING_SIDE,
                "Q": WHITE_QUEEN_SIDE,
                "k": BLACK_KING_SIDE,
                "q": BLACK_QUEEN_SIDE,
            }
            if any(symbol not in symbols for symbol in castling) or len(set(castling)) != len(castling):
                raise ValueError("Invalid FEN castling field")
            for symbol in castling:
                castling_rights |= symbols[symbol]

        ep_square = None if ep == "-" else parse_square(ep)
        if ep_square is not None:
            expected_row = 2 if active_color == "w" else 5
            if ep_square >> 4 != expected_row:
                raise ValueError("FEN en-passant square is on the wrong rank for the active color")

        self.squares = squares
        self.piece_squares = piece_squares
        self.king_squares = king_squares
        self.side_to_move = WHITE if active_color == "w" else BLACK
        self.castling_rights = castling_rights
        self.en_passant_square = ep_square
        self.halfmove_clock = halfmove
        self.fullmove_number = fullmove
        self.undo_stack = []
        self.null_stack: list[tuple[int | None, int, int]] = []
        self.zobrist_hash = self.compute_zobrist_hash()
        self.position_hashes = [self.zobrist_hash]

    def to_fen(self) -> str:
        ranks: list[str] = []
        for row in range(8):
            rank: list[str] = []
            empty_count = 0
            for file_index in range(8):
                piece = self.squares[row * 16 + file_index]
                if piece == EMPTY:
                    empty_count += 1
                    continue
                if empty_count:
                    rank.append(str(empty_count))
                    empty_count = 0
                symbol = PIECE_TO_CHAR[abs(piece)]
                rank.append(symbol if piece > 0 else symbol.lower())
            if empty_count:
                rank.append(str(empty_count))
            ranks.append("".join(rank))

        active_color = "w" if self.side_to_move == WHITE else "b"
        castling = "".join(
            symbol
            for right, symbol in (
                (WHITE_KING_SIDE, "K"),
                (WHITE_QUEEN_SIDE, "Q"),
                (BLACK_KING_SIDE, "k"),
                (BLACK_QUEEN_SIDE, "q"),
            )
            if self.castling_rights & right
        ) or "-"
        ep = "-" if self.en_passant_square is None else square_name(self.en_passant_square)
        return f"{'/'.join(ranks)} {active_color} {castling} {ep} {self.halfmove_clock} {self.fullmove_number}"

    def piece_at(self, square: int) -> int:
        if not is_valid_square(square):
            raise ValueError(f"Invalid 0x88 square: {square}")
        return self.squares[square]

    def _put_piece(self, piece: int, square: int) -> None:
        if piece == EMPTY:
            raise ValueError("Cannot place an empty piece")
        if not is_valid_square(square) or self.squares[square] != EMPTY:
            raise ValueError("Target square is invalid or occupied")
        self.squares[square] = piece
        self.piece_squares[piece].add(square)
        if abs(piece) == KING:
            self.king_squares[WHITE if piece > 0 else BLACK] = square

    def _remove_piece(self, square: int) -> int:
        piece = self.squares[square]
        if piece != EMPTY:
            self.squares[square] = EMPTY
            self.piece_squares[piece].remove(square)
            if abs(piece) == KING:
                self.king_squares[WHITE if piece > 0 else BLACK] = -1
        return piece

    def _has_legal_en_passant_capture(self) -> bool:
        target = self.en_passant_square
        if target is None:
            return False
        color = self.side_to_move
        source_squares = (target + 15, target + 17) if color == WHITE else (target - 15, target - 17)
        captured_square = target + (16 if color == WHITE else -16)
        for source in source_squares:
            if not is_valid_square(source) or self.squares[source] != color * PAWN:
                continue
            if self.squares[captured_square] != -color * PAWN:
                continue
            king_square = self.king_squares[color]
            self.squares[source] = EMPTY
            self.squares[captured_square] = EMPTY
            self.squares[target] = color * PAWN
            attacked = self.is_square_attacked(king_square, -color)
            self.squares[target] = EMPTY
            self.squares[captured_square] = -color * PAWN
            self.squares[source] = color * PAWN
            if not attacked:
                return True
        return False

    def compute_zobrist_hash(self) -> int:
        value = ZOBRIST.castling[self.castling_rights]
        if self.side_to_move == BLACK:
            value ^= ZOBRIST.black_to_move
        for square in range(128):
            if square & 0x88:
                continue
            piece = self.squares[square]
            if piece != EMPTY:
                value ^= ZOBRIST.piece_square[_piece_key_index(piece)][square]
        if self._has_legal_en_passant_capture():
            value ^= ZOBRIST.en_passant_file[self.en_passant_square & 7]
        return value

    def _toggle_piece_hash(self, piece: int, square: int) -> None:
        self.zobrist_hash ^= ZOBRIST.piece_square[_piece_key_index(piece)][square]

    def make_move(self, move: Move) -> UndoState:
        from_square, to_square = move.from_square, move.to_square
        if not is_valid_square(from_square) or not is_valid_square(to_square):
            raise ValueError("Move contains an invalid square")
        moving_piece = self.squares[from_square]
        if moving_piece == EMPTY or (WHITE if moving_piece > 0 else BLACK) != self.side_to_move:
            raise ValueError("Move source does not contain a piece of the side to move")
        if move.promotion is not None and move.promotion not in PROMOTION_TYPES:
            raise ValueError("Invalid promotion piece")

        captured_square = to_square
        captured_piece = self.squares[to_square]
        if captured_piece != EMPTY and (WHITE if captured_piece > 0 else BLACK) == self.side_to_move:
            raise ValueError("A move cannot capture a friendly piece")
        is_en_passant = abs(moving_piece) == PAWN and to_square == self.en_passant_square and captured_piece == EMPTY and (from_square & 7) != (to_square & 7)
        if is_en_passant:
            captured_square = to_square + (16 if self.side_to_move == WHITE else -16)
            captured_piece = self.squares[captured_square]
            if captured_piece != -self.side_to_move * PAWN:
                raise ValueError("Invalid en-passant capture")
        if abs(captured_piece) == KING:
            raise ValueError("A king cannot be captured")
        is_castling = abs(moving_piece) == KING and abs(to_square - from_square) == 2
        if is_castling:
            rook_from = from_square + (3 if to_square > from_square else -4)
            if captured_piece != EMPTY or self.squares[rook_from] != self.side_to_move * ROOK:
                raise ValueError("Castling requires an empty destination and a rook on its starting square")

        state = UndoState(
            move=move,
            moving_piece=moving_piece,
            captured_piece=captured_piece,
            captured_square=captured_square,
            castling_rights=self.castling_rights,
            en_passant_square=self.en_passant_square,
            halfmove_clock=self.halfmove_clock,
            fullmove_number=self.fullmove_number,
            side_to_move=self.side_to_move,
            zobrist_hash=self.zobrist_hash,
        )
        self.undo_stack.append(state)

        self.zobrist_hash ^= ZOBRIST.castling[self.castling_rights]
        if self._has_legal_en_passant_capture():
            self.zobrist_hash ^= ZOBRIST.en_passant_file[self.en_passant_square & 7]

        self._toggle_piece_hash(moving_piece, from_square)
        self._remove_piece(from_square)
        if captured_piece != EMPTY:
            self._toggle_piece_hash(captured_piece, captured_square)
            self._remove_piece(captured_square)

        placed_piece = moving_piece if move.promotion is None else self.side_to_move * move.promotion
        self._put_piece(placed_piece, to_square)
        self._toggle_piece_hash(placed_piece, to_square)

        if is_castling:
            if to_square > from_square:
                rook_from, rook_to = from_square + 3, from_square + 1
            else:
                rook_from, rook_to = from_square - 4, from_square - 1
            rook = self._remove_piece(rook_from)
            self._put_piece(rook, rook_to)
            self._toggle_piece_hash(rook, rook_from)
            self._toggle_piece_hash(rook, rook_to)

        if moving_piece == WHITE * KING:
            self.castling_rights &= ~(WHITE_KING_SIDE | WHITE_QUEEN_SIDE)
        elif moving_piece == BLACK * KING:
            self.castling_rights &= ~(BLACK_KING_SIDE | BLACK_QUEEN_SIDE)
        self._clear_rook_right(from_square)
        if captured_piece != EMPTY:
            self._clear_rook_right(captured_square)

        self.en_passant_square = None
        if abs(moving_piece) == PAWN and abs(to_square - from_square) == 32:
            self.en_passant_square = (to_square + from_square) // 2

        if abs(moving_piece) == PAWN or captured_piece != EMPTY:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1
        if self.side_to_move == BLACK:
            self.fullmove_number += 1
        self.side_to_move = -self.side_to_move

        self.zobrist_hash ^= ZOBRIST.castling[self.castling_rights]
        if self._has_legal_en_passant_capture():
            self.zobrist_hash ^= ZOBRIST.en_passant_file[self.en_passant_square & 7]
        self.zobrist_hash ^= ZOBRIST.black_to_move
        self.position_hashes.append(self.zobrist_hash)
        return state

    def make_null_move(self) -> None:
        """Pass the turn (search only). Must be undone with ``unmake_null_move``.

        Clears the en-passant square, advances the halfmove clock and keeps the
        incremental hash and the repetition history consistent.
        """
        key = self.zobrist_hash
        if self.en_passant_square is not None and self._has_legal_en_passant_capture():
            key ^= ZOBRIST.en_passant_file[self.en_passant_square & 7]
        key ^= ZOBRIST.black_to_move
        self.null_stack.append((self.en_passant_square, self.halfmove_clock, self.zobrist_hash))
        self.en_passant_square = None
        self.halfmove_clock += 1
        self.side_to_move = -self.side_to_move
        self.zobrist_hash = key
        self.position_hashes.append(key)

    def unmake_null_move(self) -> None:
        if not self.null_stack:
            raise ValueError("No null move to undo")
        self.en_passant_square, self.halfmove_clock, self.zobrist_hash = self.null_stack.pop()
        self.side_to_move = -self.side_to_move
        self.position_hashes.pop()

    def _clear_rook_right(self, square: int) -> None:
        self.castling_rights &= ~ROOK_RIGHT_BY_SQUARE.get(square, 0)

    def unmake_move(self) -> Move:
        if not self.undo_stack:
            raise ValueError("No move to undo")
        state = self.undo_stack.pop()
        move = state.move

        moved_piece = self._remove_piece(move.to_square)
        if abs(state.moving_piece) == KING and abs(move.to_square - move.from_square) == 2:
            if move.to_square > move.from_square:
                rook_from, rook_to = move.from_square + 3, move.from_square + 1
            else:
                rook_from, rook_to = move.from_square - 4, move.from_square - 1
            rook = self._remove_piece(rook_to)
            self._put_piece(rook, rook_from)

        self._put_piece(state.moving_piece, move.from_square)
        if state.captured_piece != EMPTY:
            self._put_piece(state.captured_piece, state.captured_square)

        self.castling_rights = state.castling_rights
        self.en_passant_square = state.en_passant_square
        self.halfmove_clock = state.halfmove_clock
        self.fullmove_number = state.fullmove_number
        self.side_to_move = state.side_to_move
        self.zobrist_hash = state.zobrist_hash
        self.position_hashes.pop()
        return move

    def _attacks_from_pawn(self, square: int, by_color: int, target: int) -> bool:
        deltas = (-17, -15) if by_color == WHITE else (15, 17)
        return target - square in deltas

    def is_square_attacked(self, square: int, by_color: int) -> bool:
        if not is_valid_square(square):
            raise ValueError(f"Invalid 0x88 square: {square}")

        pawn_sources = (square + 15, square + 17) if by_color == WHITE else (square - 15, square - 17)
        if any(is_valid_square(src) and self.squares[src] == by_color * PAWN for src in pawn_sources):
            return True

        for delta in (-33, -31, -18, -14, 14, 18, 31, 33):
            source = square + delta
            if is_valid_square(source) and self.squares[source] == by_color * KNIGHT:
                return True

        for delta in (-17, -16, -15, -1, 1, 15, 16, 17):
            source = square + delta
            if is_valid_square(source) and self.squares[source] == by_color * KING:
                return True

        for directions, sliders in (
            ((-17, -15, 15, 17), (BISHOP, QUEEN)),
            ((-16, -1, 1, 16), (ROOK, QUEEN)),
        ):
            for delta in directions:
                source = square + delta
                while is_valid_square(source):
                    piece = self.squares[source]
                    if piece != EMPTY:
                        if (WHITE if piece > 0 else BLACK) == by_color and abs(piece) in sliders:
                            return True
                        break
                    source += delta
        return False

    def in_check(self, color: int | None = None) -> bool:
        color = self.side_to_move if color is None else color
        king_square = self.king_squares[color]
        return self.is_square_attacked(king_square, -color)

    def is_threefold_repetition(self) -> bool:
        current_index = len(self.position_hashes) - 1
        matches = 1
        earliest = max(0, current_index - self.halfmove_clock)
        for index in range(current_index - 2, earliest - 1, -2):
            if self.position_hashes[index] == self.zobrist_hash:
                matches += 1
                if matches >= 3:
                    return True
        return False

    def is_fifty_move_draw(self) -> bool:
        return self.halfmove_clock >= 100

    def is_insufficient_material(self) -> bool:
        piece_squares = self.piece_squares
        # Fast exit (this runs at every search node): any pawn, rook or queen
        # means mating material exists.
        if (
            piece_squares[PAWN]
            or piece_squares[-PAWN]
            or piece_squares[ROOK]
            or piece_squares[-ROOK]
            or piece_squares[QUEEN]
            or piece_squares[-QUEEN]
        ):
            return False
        non_king_pieces = [
            (piece, square)
            for piece, squares in self.piece_squares.items()
            if abs(piece) != KING
            for square in squares
        ]
        if not non_king_pieces:
            return True
        if any(abs(piece) in (PAWN, ROOK, QUEEN) for piece, _ in non_king_pieces):
            return False
        if len(non_king_pieces) == 1:
            return abs(non_king_pieces[0][0]) in (BISHOP, KNIGHT)
        if all(abs(piece) == BISHOP for piece, _ in non_king_pieces):
            square_colors = {(((square & 7) + (square >> 4)) & 1) for _, square in non_king_pieces}
            return len(square_colors) == 1
        return False

    def is_checkmate(self) -> bool:
        if not self.in_check():
            return False
        from engine.movegen import generate_legal_moves

        return not next(generate_legal_moves(self), None)

    def is_stalemate(self) -> bool:
        if self.in_check():
            return False
        from engine.movegen import generate_legal_moves

        return not next(generate_legal_moves(self), None)

    def is_draw(self) -> bool:
        return (
            self.is_fifty_move_draw()
            or self.is_threefold_repetition()
            or self.is_insufficient_material()
            or self.is_stalemate()
        )
