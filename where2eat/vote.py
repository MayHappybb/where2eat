from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from werkzeug.exceptions import abort
from time import localtime

from where2eat.auth import login_required
from where2eat.db import get_db
from where2eat.extensions import scheduler

bp = Blueprint('vote', __name__)

refreshtime = 13 # vote refresh time

@bp.route('/')
@login_required
def index():
    db = get_db()
    eatens = db.execute(
        'SELECT canteen, COUNT(*) as eat_times from eaten WHERE teamid = ? GROUP BY canteen',
        (g.user['teamid'],)
    ).fetchall()
    return render_template('vote/index.html', eatens=eatens)

@bp.route('/vote', methods=('GET', 'POST'))
@login_required
def vote():
    if request.method == 'POST':
        canteen = request.json['canteen']
        error = None

        db = get_db()
        voted = db.execute(
            'SELECT * FROM vote WHERE (author_id, eatdate, meal, canteen) = (?, date("now"), ?, ?)',
            (g.user['id'], 'lunch' if localtime().tm_hour < refreshtime else 'dinner', canteen)
        ).fetchone()
        
        if voted is not None:
            error = 'You have already voted for this canteen.'

        if not canteen:
            error = 'Canteen is required.'

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                'INSERT INTO vote (canteen, teamid, author_id, eatdate, meal)'
                ' VALUES (?, ?, ?, date("now"), ?)',
                (canteen, g.user['teamid'], g.user['id'], 'lunch' if localtime().tm_hour < refreshtime else 'dinner')
            )
            db.commit()
            return redirect(url_for('vote.vote'))

    db = get_db()
    votes = db.execute(
        'SELECT canteen, COUNT(*) AS vote_num FROM vote WHERE (teamid, eatdate, meal) = (?, date("now"), ?) GROUP BY canteen ORDER BY vote_num DESC',
        (g.user['teamid'], 'lunch' if localtime().tm_hour < refreshtime else 'dinner')
    ).fetchall()

    voted = db.execute(
        'SELECT canteen, COUNT(*) AS vote_num FROM vote WHERE author_id = ? GROUP BY canteen ORDER BY vote_num DESC',
        (g.user['id'],)
    ).fetchall()

    return render_template('vote/vote.html', votes=votes, voted=voted)

@scheduler.task('cron', id='refresh_voted', hour=23)
def refresh_voted():
    with scheduler.app.app_context():
        db = get_db()
        db.execute(
            'INSERT into eaten (teamid, eatdate, meal, canteen, votes) SELECT teamid, eatdate, meal, canteen, MAX(vote_num) as vote_num FROM (SELECT teamid, eatdate, meal, canteen, COUNT(canteen) as vote_num FROM vote WHERE eatdate = date("now") GROUP BY teamid, eatdate, meal, canteen) GROUP by teamid, eatdate, meal'
        )
        db.commit()