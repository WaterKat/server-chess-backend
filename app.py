from flask import Flask, request, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from uuid import uuid4

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chess.db'
db = SQLAlchemy(app)

class Game(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  black_id=db.Column(db.String(200), nullable=False, default='black')
  white_id=db.Column(db.String(200), nullable=False, default='white')
  content = db.Column(db.String(200), nullable=False, default='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
  last_play_date = db.Column(db.DateTime, default=datetime.utcnow)
  date_created = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
  db.create_all()

@app.route('/game', methods=['POST'])
def create_game():
  new_game = Game()
  new_game.black_id = str(uuid4())
  new_game.white_id = str(uuid4())
  
  try:
    db.session.add(new_game)
    db.session.commit()
    
  except Exception as err:
    return 'Something went wrong creating your game.'
  
  return redirect(f"/game/{new_game.white_id}")


@app.route('/', methods=['GET'])
def index():
  active_games = Game.query.order_by(Game.last_play_date).all()
  return render_template('index.html', active_games=active_games)

if __name__ == "__main__":
  app.run(debug=True)
