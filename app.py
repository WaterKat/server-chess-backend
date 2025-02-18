from flask import Flask, Blueprint, request, render_template, redirect, make_response, url_for, g
from flask_sqlalchemy import SQLAlchemy

from urllib.parse import urlparse, urlencode

from uuid import uuid4

from datetime import datetime, timezone, timedelta
from enum import Enum

# env
import os
from dotenv import load_dotenv

load_dotenv()

# jwt
import jwt


# chess
import chess


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chess.db"
db = SQLAlchemy(app)
chess_bp = Blueprint('chess', __name__, url_prefix='/chess', static_folder='static', static_url_path='static')


class COOKIE_KEYS(Enum):
    JWT = "player_data"


JWT_SECRET = os.getenv("JWT_SECRET_KEY")
if JWT_SECRET is None:
    raise ValueError("JWT_SECRET_KEY is not set in the environment.")


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.String(200), nullable=False, default="0")
    private_id = db.Column(db.String(200), nullable=False, default=str(uuid4()))
    white_id = db.Column(db.String(200), nullable=False, default=f"_{str(uuid4())}")
    black_id = db.Column(db.String(200), nullable=False, default=f"_{str(uuid4())}")
    content = db.Column(
        db.String(200),
        nullable=False,
        default=chess.Board().fen(),
    )
    last_play_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    date_created = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(200), nullable=False, default=str(uuid4()))
    username = db.Column(db.String(200), nullable=False, default="Player")
    date_created = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.String(200), nullable=False)
    content = db.Column(db.String(200), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class UserJWTData:
    user_id: str = "0"

    def to_dict(self):
        return {"user_id": self.user_id}


with app.app_context():
    db.create_all()


# ? tool functions
def update_dict_without_addition(d, u):
    c = d.copy()
    for k, v in u.items():
        if k in c:
            c[k] = v
    return c


def create_default_jwt_token_object():
    return {"user_id": str(uuid4())}


# MARK: before request
@chess_bp.before_request
def load_user():
    # ? init player data
    g.user = None

    # ? don't update jwt if not needed
    if request.path == url_for("chess.create_user"):
        return  # not redirect

    # ? create redirect response
    redirect_response = redirect(url_for("chess.create_user", next=request.url))

    # ? check jwt
    try:
        user_jwt_cookie = request.cookies.get(COOKIE_KEYS.JWT.value)
        user_jwt_object = jwt.decode(user_jwt_cookie, JWT_SECRET, algorithms=["HS256"])
        g.user = User.query.filter_by(user_id=user_jwt_object.get("user_id")).first()
        if g.user is not None:
            g.user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            return  # don't redirect
    except Exception as err:
        print("Redirecting", err)
        pass
    return redirect_response


# MARK: create user
@chess_bp.route("/create_user", methods=["GET"])
def create_user():
    # ? get next url, check if same url to prevent redirect loop
    query_next_url = request.args.get("next") or url_for("chess.index")
    parsed_query_url = urlparse(query_next_url)
    if (
        parsed_query_url.path == url_for("chess.create_user")
        and parsed_query_url.netloc == request.host
    ):
        query_next_url = url_for("chess.index")
    redirect_response = make_response(redirect(query_next_url))

    # ? get jwt cookie
    try:
        user_jwt_cookie = request.cookies.get(COOKIE_KEYS.JWT.value)
        user_jwt_object = jwt.decode(user_jwt_cookie, JWT_SECRET, algorithms=["HS256"])
        g.user = User.query.filter_by(user_id=user_jwt_object.get("user_id")).first()
        if g.user is not None:
            return redirect_response
    except Exception as err:
        print("Creating new user", err)
        pass

    # ? create new user
    try:
        g.user = User()
        db.session.add(g.user)
        db.session.commit()
        new_jwt_object = UserJWTData()
        new_jwt_object.user_id = g.user.user_id
        new_jwt_cookie = jwt.encode(
            new_jwt_object.to_dict(), JWT_SECRET, algorithm="HS256"
        )
        redirect_response.set_cookie(
            key=COOKIE_KEYS.JWT.value, value=new_jwt_cookie, secure=True
        )
        return redirect_response
    except Exception as err:
        print("Error creating user", err)
        return "Something went wrong creating your user."


# MARK: change username
@chess_bp.route("/api/change_username", methods=["POST"])
def change_username():
    try:
        g.user.username = request.form.get("new_username") or "Player"
        db.session.commit()
        return "Username updated."
    except Exception as err:
        print("Error updating username", err)
        return "Something went wrong updating your username."


# MARK: create game
@chess_bp.route("/api/create_game", methods=["POST"])
def create_game():
    try:
        if g.user is None:
            raise ValueError("User not found.")
        new_game = Game()
        new_game.owner_id = g.user.user_id
        db.session.add(new_game)
        db.session.commit()
        return redirect(url_for("chess.manage_game", game_id=new_game.id))
    except Exception as err:
        print("Error creating game", err)
        return "Something went wrong creating your game."


# MARK: manage game
@chess_bp.route("/api/manage_game/<game_id>", methods=["GET"])
def manage_game(game_id):
    if g.user is None:
        return "User not found."
    if game_id is None:
        return "Game not found."
    game = Game.query.filter_by(id=game_id, owner_id=g.user.user_id).first()
    if game is None:
        return "Something went wrong getting your game."

    urls = {
        "white_available": game.white_id.startswith("_"),
        "white_url": (
            url_for(
                "join_game", private_game_id=game.private_id, entry_key=game.white_id
            )
            if game.white_id.startswith("_")
            else User.query.filter_by(user_id=game.white_id).first().username
            or "Player"
        ),
        "black_available": game.black_id.startswith("_"),
        "black_url": (
            url_for(
                "join_game", private_game_id=game.private_id, entry_key=game.black_id
            )
            if game.black_id.startswith("_")
            else User.query.filter_by(user_id=game.black_id).first().username
            or "Player"
        ),
    }

    return render_template("manage.html", game=game, urls=urls)


# MARK: join game
@chess_bp.route("/api/join_game/<private_game_id>/<entry_key>", methods=["GET"])
def join_game(private_game_id, entry_key):
    if g.user is None:
        return "User not found."
    if private_game_id is None:
        return "Game not found."

    # ? unclaimed players start with "_" in their id
    if not entry_key.startswith("_"):
        return "Player already claimed"  # ? already claimed

    player_string = entry_key
    game = Game.query.filter(
        (Game.private_id == private_game_id),
        (Game.white_id == player_string) | (Game.black_id == player_string),
    ).first()

    if game is None:
        return "Game not found."

    if game.white_id == player_string:
        game.white_id = g.user.user_id
    elif game.black_id == player_string:
        game.black_id = g.user.user_id
    else:
        return "Invalid entry key."

    db.session.commit()
    return redirect(url_for("chess.play_game", game_id=game.id))


# MARK: play game
@chess_bp.route("/play_game/<game_id>", methods=["GET", "POST"])
def play_game(game_id):
    if g.user is None:
        return "User not found."
    if game_id is None:
        return "Game not found."
    game = Game.query.filter_by(id=game_id).first()
    if game is None:
        return "Game not found."
    if (game.white_id != g.user.user_id) and (game.black_id != g.user.user_id):
        return render_template("spectate.html", game=game)

    selected_row = request.form.get("row")
    selected_column = request.form.get("column")
    selected = None
    try:
        selected = (chr(ord('a') + int(selected_row)), 
                    chr(ord('8') - int(selected_column)))
        pass
    except Exception as err:
      pass

    if not selected_row is None and not selected_column is None:
      row_num = int(selected_row)
      selected = (selected_row, selected_column)

    print("play requested", (selected_row, selected_column))

    raw_board_content = str(chess.Board(game.content))
    raw_board_content_rows = raw_board_content.split("\n")
    board_content_items = []
    for row_index, row in enumerate(raw_board_content_rows):
        raw_board_content_column = row.split(" ")
        board_row = []
        for column_index, piece in enumerate(raw_board_content_column):
            piece_data = {
                "piece": piece if piece != "." else "",
                "row": row_index,
                "column": column_index,
                "board_is_white": ((row_index + column_index) % 2 == 0),
                "is_white": piece.isupper(),
                "is_selected": (str(selected_row) == str(row_index))
                and (str(selected_column) == str(column_index)),
                "is_valid_location": False,
                "action_link": url_for("chess.play_game", game_id=game_id),
            }
            if (piece_data.get("is_selected")):
                print("selected: ", piece_data)
            board_row.append(piece_data)
        board_content_items.append(board_row)
    return render_template("game.html", game=game, board_content=board_content_items)


@chess_bp.route("/game/<user_id>", methods=["GET", "POST"])
def get_playable_game(user_id):
    if request.method == "POST":
        pass

    else:
        game_with_link = Game.query.filter_by(white_id=user_id).first()
        color = "white"
        if game_with_link is None:
            game_with_link = Game.query.filter_by(black_id=user_id).first()
            color = "black"
        if game_with_link is None:
            return "Something went wrong getting your game."
        return render_template("game.html", game=game_with_link, color=color)


@chess_bp.route("/spectate/<int:id>")
def get_spectating_game(id):
    pass


@chess_bp.route("/", methods=["GET"])
def index():
    active_games = Game.query.order_by(Game.last_play_date).all()
    return render_template("index.html", active_games=active_games)


app.register_blueprint(chess_bp)


if __name__ == "__main__":
    is_debug = False
    app.run(host="0.0.0.0" if not is_debug else "127.0.0.1", debug=is_debug, port=3000)
