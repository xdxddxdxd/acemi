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


def _pawn_moves(board: Board, square: int, color: int) -> Iterator[Move]:
    direction = -16 if color == WHITE else 16
    start_row = 6 if color == WHITE else 1
    promotion_row = 0 if color == WHITE else 7
    one_step = square + direction

    if is_valid_square(one_step) and board.squares[one_step] == EMPTY:
        if one_step >> 4 == promotion_row:
            for promotion in PROMOTION_TYPES:
                yield Move(square, one_step, promotion)
        else:
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
                for promotion in PROMOTION_TYPES:
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


def generate_pseudo_legal_moves(board: Board) -> Iterator[Move]:
    """Yield moves that follow piece movement rules but may leave the king checked."""
    color = board.side_to_move
    for square in range(128):
        if square & 0x88:
            continue
        piece = board.squares[square]
        if piece == EMPTY or (WHITE if piece > 0 else BLACK) != color:
            continue
        piece_type = abs(piece)

        if piece_type == PAWN:
            yield from _pawn_moves(board, square, color)
        elif piece_type == KNIGHT:
            for delta in KNIGHT_OFFSETS:
                target = square + delta
                if not is_valid_square(target):
                    continue
                target_piece = board.squares[target]
                if target_piece == EMPTY or (WHITE if target_piece > 0 else BLACK) == -color:
                    if abs(target_piece) != KING:
                        yield Move(square, target)
        elif piece_type in (BISHOP, ROOK, QUEEN):
            directions = (
                BISHOP_DIRECTIONS if piece_type == BISHOP
                else ROOK_DIRECTIONS if piece_type == ROOK
                else BISHOP_DIRECTIONS + ROOK_DIRECTIONS
            )
            for delta in directions:
                target = square + delta
                while is_valid_square(target):
                    target_piece = board.squares[target]
                    if target_piece == EMPTY:
                        yield Move(square, target)
                    else:
                        if (WHITE if target_piece > 0 else BLACK) == -color and abs(target_piece) != KING:
                            yield Move(square, target)
                        break
                    target += delta
        elif piece_type == KING:
            for delta in KING_OFFSETS:
                target = square + delta
                if not is_valid_square(target):
                    continue
                target_piece = board.squares[target]
                if target_piece == EMPTY or (
                    (WHITE if target_piece > 0 else BLACK) == -color and abs(target_piece) != KING
                ):
                    yield Move(square, target)
            yield from _castling_moves(board, color, square)


def generate_legal_moves(board: Board) -> Iterator[Move]:
    """Yield moves that do not leave the moving side's king in check."""
    moving_color = board.side_to_move
    for move in generate_pseudo_legal_moves(board):
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
