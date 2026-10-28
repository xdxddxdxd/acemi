"""Pseudo-legal and legal move generation for the 0x88 board."""

from __future__ import annotations

from collections.abc import Iterator

from engine.board import (
    BISHOP,
    BLACK,
    EMPTY,
    KING,
    KNIGHT,
    PAWN,
    PROMOTION_TYPES,
    QUEEN,
    ROOK,
    WHITE,
    WHITE_KING_SIDE,
    WHITE_QUEEN_SIDE,
    BLACK_KING_SIDE,
    BLACK_QUEEN_SIDE,
    Board,
    Move,
    is_valid_square,
)

KNIGHT_OFFSETS = (-33, -31, -18, -14, 14, 18, 31, 33)
KING_OFFSETS = (-17, -16, -15, -1, 1, 15, 16, 17)
BISHOP_DIRECTIONS = (-17, -15, 15, 17)
ROOK_DIRECTIONS = (-16, -1, 1, 16)
ALL_DIRECTIONS = BISHOP_DIRECTIONS + ROOK_DIRECTIONS
PIECE_ORDER = (PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING)

# Note on ``target & 0x88``: every target is square + a small offset, so it lies
# in -33..160. In that range a square is off the board exactly when the 0x88 test
# is non-zero (negative numbers and numbers above 127 always have bit 7 set).


def _pawn_moves(board: Board, square: int, color: int, captures_only: bool) -> Iterator[Move]:
    direction = -16 if color == WHITE else 16
    start_row = 6 if color == WHITE else 1
    promotion_row = 0 if color == WHITE else 7
    one_step = square + direction
    # Quiescence-style generation only needs queen promotions.
    promotions = (QUEEN,) if captures_only else PROMOTION_TYPES

    if is_valid_square(one_step) and board.squares[one_step] == EMPTY:
        if one_step >> 4 == promotion_row:
            for promotion in promotions:
                yield Move(square, one_step, promotion)
        elif not captures_only:
            yield Move(square, one_step)
            two_steps = one_step + direction
            if square >> 4 == start_row and board.squares[two_steps] == EMPTY:
                yield Move(square, two_steps)

    for delta in (direction - 1, direction + 1):
        target = square + delta
        if not is_valid_square(target):
            continue
        target_piece = board.squares[target]
        if target_piece != EMPTY and (WHITE if target_piece > 0 else BLACK) == -color:
            if abs(target_piece) == KING:
                continue
            if target >> 4 == promotion_row:
                for promotion in promotions:
                    yield Move(square, target, promotion)
            else:
                yield Move(square, target)
        elif target == board.en_passant_square:
            yield Move(square, target)


def _castling_moves(board: Board, color: int, king_square: int) -> Iterator[Move]:
    opponent = -color
    home_square = 116 if color == WHITE else 4
    if king_square != home_square:
        return
    if color == WHITE:
        king_right, queen_right = WHITE_KING_SIDE, WHITE_QUEEN_SIDE
    else:
        king_right, queen_right = BLACK_KING_SIDE, BLACK_QUEEN_SIDE

    if board.is_square_attacked(king_square, opponent):
        return

    if board.castling_rights & king_right:
        transit = king_square + 1
        destination = king_square + 2
        rook_square = king_square + 3
        if (
            is_valid_square(rook_square)
            and board.squares[rook_square] == color * ROOK
            and board.squares[transit] == EMPTY
            and board.squares[destination] == EMPTY
            and not board.is_square_attacked(transit, opponent)
            and not board.is_square_attacked(destination, opponent)
        ):
            yield Move(king_square, destination)

    if board.castling_rights & queen_right:
        transit = king_square - 1
        destination = king_square - 2
        rook_square = king_square - 4
        empty_square = king_square - 3
        if (
            is_valid_square(rook_square)
            and board.squares[rook_square] == color * ROOK
            and board.squares[transit] == EMPTY
            and board.squares[destination] == EMPTY
            and board.squares[empty_square] == EMPTY
            and not board.is_square_attacked(transit, opponent)
            and not board.is_square_attacked(destination, opponent)
        ):
            yield Move(king_square, destination)


def generate_pseudo_legal_moves(board: Board, captures_only: bool = False) -> Iterator[Move]:
    """Yield moves that follow piece movement rules but may leave the king checked.

    With ``captures_only`` only captures, en passant and queen promotions are
    produced (no quiet moves, no castling); this is what quiescence search uses.
    """
    color = board.side_to_move
    squares = board.squares
    piece_squares = board.piece_squares
    # Snapshot the piece list first: callers make/unmake moves between yields,
    # which mutates the sets. Sorting keeps the move order independent of the
    # make/unmake history.
    own_pieces = [
        (piece_type, square)
        for piece_type in PIECE_ORDER
        for square in sorted(piece_squares[color * piece_type])
    ]

    for piece_type, square in own_pieces:
        if piece_type == PAWN:
            yield from _pawn_moves(board, square, color, captures_only)
        elif piece_type == KNIGHT or piece_type == KING:
            offsets = KNIGHT_OFFSETS if piece_type == KNIGHT else KING_OFFSETS
            for delta in offsets:
                target = square + delta
                if target & 0x88:
                    continue
                target_piece = squares[target]
                if target_piece == EMPTY:
                    if not captures_only:
                        yield Move(square, target)
                elif target_piece * color < 0 and abs(target_piece) != KING:
                    yield Move(square, target)
            if piece_type == KING and not captures_only:
                yield from _castling_moves(board, color, square)
        else:
            if piece_type == BISHOP:
                directions = BISHOP_DIRECTIONS
            elif piece_type == ROOK:
                directions = ROOK_DIRECTIONS
            else:
                directions = ALL_DIRECTIONS
            for delta in directions:
                target = square + delta
                while not target & 0x88:
                    target_piece = squares[target]
                    if target_piece == EMPTY:
                        if not captures_only:
                            yield Move(square, target)
                    else:
                        if target_piece * color < 0 and abs(target_piece) != KING:
                            yield Move(square, target)
                        break
                    target += delta


def generate_legal_moves(board: Board, captures_only: bool = False) -> Iterator[Move]:
    """Yield moves that do not leave the moving side's king in check."""
    moving_color = board.side_to_move
    for move in generate_pseudo_legal_moves(board, captures_only):
        board.make_move(move)
        legal = not board.is_square_attacked(board.king_squares[moving_color], -moving_color)
        board.unmake_move()
        if legal:
            yield move


def find_legal_move(board: Board, uci: str) -> Move:
    """Find a legal move by UCI notation, such as ``e2e4`` or ``a7a8q``."""
    normalized = uci.strip().lower()
    for move in generate_legal_moves(board):
        if move.uci() == normalized:
            return move
    raise ValueError(f"Illegal move in position: {uci}")


def perft(board: Board, depth: int) -> int:
    """Count legal move-tree leaf nodes, as used by standard chess perft."""
    if depth < 0:
        raise ValueError("Perft depth cannot be negative")
    if depth == 0:
        return 1
    nodes = 0
    for move in generate_legal_moves(board):
        board.make_move(move)
        nodes += perft(board, depth - 1)
        board.unmake_move()
    return nodes


def perft_divide(board: Board, depth: int) -> dict[str, int]:
    """Return the leaf count beneath each root move to help diagnose perft errors."""
    if depth < 1:
        raise ValueError("Perft divide depth must be at least 1")
    result: dict[str, int] = {}
    for move in generate_legal_moves(board):
        board.make_move(move)
        result[move.uci()] = perft(board, depth - 1)
        board.unmake_move()
    return result


def perft_stats(board: Board, depth: int) -> dict[str, int]:
    """Count leaf-node move categories (captures, en passant, castles, promotions, checks)."""
    if depth < 1:
        raise ValueError("Perft stats depth must be at least 1")
    stats = {"nodes": 0, "captures": 0, "en_passant": 0, "castles": 0, "promotions": 0, "checks": 0}

    def visit(remaining: int) -> None:
        for move in generate_legal_moves(board):
            moving_piece = board.squares[move.from_square]
            is_ep = (
                abs(moving_piece) == PAWN
                and move.to_square == board.en_passant_square
                and board.squares[move.to_square] == EMPTY
                and (move.from_square & 7) != (move.to_square & 7)
            )
            is_capture = board.squares[move.to_square] != EMPTY or is_ep
            is_castle = abs(moving_piece) == KING and abs(move.to_square - move.from_square) == 2
            board.make_move(move)
            if remaining == 1:
                stats["nodes"] += 1
                stats["captures"] += int(is_capture)
                stats["en_passant"] += int(is_ep)
                stats["castles"] += int(is_castle)
                stats["promotions"] += int(move.promotion is not None)
                stats["checks"] += int(board.in_check())
            else:
                visit(remaining - 1)
            board.unmake_move()

    visit(depth)
    return stats
