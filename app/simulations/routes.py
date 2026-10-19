"""Workplace simulation catalogue and learner response-submission routes.

Learner access is restricted to simulations linked to their enrolled program.
A simulation with no learning links is admin-only until it is linked.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from app.common.security import permission_required, current_user
from app.extensions import db
from app.models import Simulation, SimulationAttempt, Enrollment

simulations_bp = Blueprint("simulations", __name__, url_prefix="/simulations")


def simulations_for_learner(user):
    """Return published simulations that match a learner's enrolled course/track program."""
    enrolled = Enrollment.query.filter_by(user_id=user.id).all()
    course_ids = {row.course_id for row in enrolled}
    courses = [row.course for row in enrolled if row.course]
    track_ids = {track.id for course in courses for track in course.tracks}
    visible = []
    for simulation in Simulation.query.filter_by(published=True).order_by(Simulation.id).all():
        # Unlinked simulations are not globally visible to learners.
        if not (simulation.tracks or simulation.courses or simulation.modules or simulation.lessons):
            continue
        if any(track.id in track_ids for track in simulation.tracks):
            visible.append(simulation); continue
        if any(course.id in course_ids for course in simulation.courses):
            visible.append(simulation); continue
        if any(module.course_id in course_ids for module in simulation.modules):
            visible.append(simulation); continue
        if any(lesson.module and lesson.module.course_id in course_ids for lesson in simulation.lessons):
            visible.append(simulation); continue
    return visible


def learner_can_access_simulation(user, simulation):
    return simulation in simulations_for_learner(user)


@simulations_bp.route("/")
@permission_required("simulations.view", "learner", "instructor", "mentor", "admin")
def index():
    user = current_user()
    if user and user.role == "learner":
        from app.learning.routes import _stage_is_unlocked
        if not _stage_is_unlocked(user, "simulation"):
            flash("Complete all Hard Skills and Soft Skills courses to unlock Work Simulation.", "warning")
            return redirect(url_for("learner.choose_learning_path"))
        simulations = simulations_for_learner(user)
    else:
        simulations = Simulation.query.filter_by(published=True).order_by(Simulation.id).all()
    return render_template("simulations/index.html", simulations=simulations)


@simulations_bp.route("/<int:simulation_id>", methods=["GET", "POST"])
@permission_required("simulations.attempt", "learner")
def detail(simulation_id):
    user = current_user()
    from app.learning.routes import _stage_is_unlocked
    if not _stage_is_unlocked(user, "simulation"):
        flash("Complete all Hard Skills and Soft Skills courses to unlock Work Simulation.", "warning")
        return redirect(url_for("learner.choose_learning_path"))
    simulation = Simulation.query.filter_by(id=simulation_id, published=True).first_or_404()
    # Enforce program scope on direct URLs as well as on the catalogue page.
    if not learner_can_access_simulation(user, simulation):
        abort(404)
    if request.method == "POST":
        response = request.form.get("response", "").strip()
        if len(response) < 20:
            flash("Please provide a more complete response.", "error")
        else:
            db.session.add(SimulationAttempt(simulation_id=simulation.id, learner_id=user.id, response=response))
            db.session.commit()
            flash("Simulation response submitted.", "success")
            return redirect(url_for("simulations.index"))
    return render_template("simulations/detail.html", simulation=simulation)
