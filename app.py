from flask import Flask, request, render_template, redirect, make_response, url_for, g
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


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chess.db"
db = SQLAlchemy(app)


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
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
    )
    last_play_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    date_created = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(200), nullable=False, default=str(uuid4()))
    username = db.Column(db.String(200), nullable=False, default="Player")
    date_created = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, default=datetime.now(timezone.utc))


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
@app.before_request
def load_user():
    # ? init player data
    g.user = None

    # ? don't update jwt if not needed
    if request.path == url_for("create_user"):
        return  # not redirect

    # ? create redirect response
    redirect_response = redirect(url_for("create_user", next=request.url))

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
@app.route("/create_user", methods=["GET"])
def create_user():
    # ? get next url, check if same url to prevent redirect loop
    query_next_url = request.args.get("next") or url_for("index")
    parsed_query_url = urlparse(query_next_url)
    if (
        parsed_query_url.path == url_for("create_user")
        and parsed_query_url.netloc == request.host
    ):
        query_next_url = url_for("index")
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
@app.route("/api/change_username", methods=["POST"])
def change_username():
    try:
        g.user.username = request.form.get("new_username") or "Player"
        db.session.commit()
        return "Username updated."
    except Exception as err:
        print("Error updating username", err)
        return "Something went wrong updating your username."


# MARK: create game
@app.route("/api/create_game", methods=["POST"])
def create_game():
    try:
        if g.user is None:
            raise ValueError("User not found.")
        new_game = Game()
        new_game.owner_id = g.user.user_id
        db.session.add(new_game)
        db.session.commit()
        return redirect(url_for("manage_game", game_id=new_game.id))
    except Exception as err:
        print("Error creating game", err)
        return "Something went wrong creating your game."


# MARK: manage game
@app.route("/api/manage_game/<game_id>", methods=["GET"])
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
@app.route("/api/join_game/<private_game_id>/<entry_key>", methods=["GET"])
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
    return redirect(url_for("play_game", game_id=game.id))


# MARK: play game
@app.route("/play_game/<game_id>", methods=["GET"])
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
    return render_template("game.html", game=game)


@app.route("/game/<user_id>", methods=["GET", "POST"])
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


@app.route("/spectate/<int:id>")
def get_spectating_game(id):
    pass


@app.route("/", methods=["GET"])
def index():
    active_games = Game.query.order_by(Game.last_play_date).all()
    return render_template("index.html", active_games=active_games)


if __name__ == "__main__":
    is_debug = False
    app.run(host="0.0.0.0" if not is_debug else "127.0.0.1", debug=is_debug)
