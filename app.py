import os
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory,
)
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'app.db')

app = Flask(__name__)
# Read config from environment for production readiness
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + DB_PATH)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')

# Security: trust proxy headers (e.g. Cloudflare, nginx). If you have an additional
# proxy in front of the app, increase the x_for/x_proto counts accordingly.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Secure cookie settings for production when using HTTPS (Cloudflare / TLS)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '1') in ('1', 'true', 'True')
app.config['REMEMBER_COOKIE_SECURE'] = os.environ.get('REMEMBER_COOKIE_SECURE', '1') in ('1', 'true', 'True')
app.config['PREFERRED_URL_SCHEME'] = 'https'

# Optional: add Flask-Talisman for HSTS and common security headers when available
try:
    from flask_talisman import Talisman
    # disable CSP by default (set policy if you serve external scripts/styles)
    Talisman(app, content_security_policy=None)
except Exception:
    # Talisman is optional; continue without it if not installed
    pass

db = SQLAlchemy(app)


class Species(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)

    def __repr__(self):
        return f"<Species {self.name}>"


class Animal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    species_id = db.Column(db.Integer, db.ForeignKey('species.id'), nullable=False)

    species = db.relationship('Species', backref=db.backref('animals', lazy=True))

    def __repr__(self):
        return f"<Animal {self.name} ({self.species.name})>"


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    bio = db.Column(db.Text)

    def __repr__(self):
        return f"<User {self.name}>"


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    caption = db.Column(db.String(300), nullable=False)
    animal_name = db.Column(db.String(100))
    notes = db.Column(db.Text)
    image_filename = db.Column(db.String(300), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    species_id = db.Column(db.Integer, db.ForeignKey('species.id'), nullable=False)
    # nullable user_id - safe migration will add column if DB created earlier
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    species = db.relationship('Species', backref=db.backref('posts', lazy=True))
    user = db.relationship('User', backref=db.backref('posts', lazy=True))

    def __repr__(self):
        return f"<Post {self.id} {self.caption[:20]}>"


def ensure_app_dirs():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def init_db():
    ensure_app_dirs()
    # Always attempt to create any missing tables for new models.
    # This is safe: create_all() will not drop existing tables.
    try:
        # wait for DB to be reachable (useful when deployed with separate DB service)
        wait_for_db(timeout=30, interval=1)
        with app.app_context():
            db.create_all()
            # ensure post table has user_id column (SQLite doesn't alter columns via create_all)
            try:
                conn = db.engine.connect()
                # check if 'user_id' exists on the posts table
                res = conn.execute("PRAGMA table_info(post);")
                cols = [row[1] for row in res]
                if 'user_id' not in cols:
                    # add nullable column
                    conn.execute('ALTER TABLE post ADD COLUMN user_id INTEGER;')
                conn.close()
            except Exception:
                app.logger.debug('Could not run ALTER TABLE to add user_id; skipping')
    except Exception as e:
        app.logger.exception('Error creating DB tables: %s', e)


def wait_for_db(timeout=30, interval=1):
    """Wait until the database is reachable or raise RuntimeError."""
    import time
    from sqlalchemy.exc import OperationalError

    start = time.time()
    while True:
        try:
            # lightweight probe
            with app.app_context():
                db.session.execute('SELECT 1')
            return True
        except OperationalError:
            if time.time() - start > timeout:
                raise RuntimeError('Database not reachable after %s seconds' % timeout)
            time.sleep(interval)


@app.route('/healthz')
def healthz():
    try:
        with app.app_context():
            db.session.execute('SELECT 1')
        return {'status': 'ok'}, 200
    except Exception as e:
        app.logger.exception('Health check failed: %s', e)
        return {'status': 'error', 'detail': str(e)}, 503


def is_editor_logged_in():
    return session.get('editor_logged_in') is True


def editor_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_editor_logged_in():
            flash('Please log in as editor to access that page.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)

    return decorated


@app.route('/')
def index():
    init_db()
    species = Species.query.order_by(Species.name).all()
    # optional filter by species
    species_filter = request.args.get('species_id')
    if species_filter:
        try:
            sid = int(species_filter)
            posts = Post.query.filter_by(species_id=sid).order_by(Post.timestamp.desc()).limit(50).all()
        except ValueError:
            posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    else:
        posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    return render_template('index.html', species=species, posts=posts)


@app.route('/login', methods=['GET', 'POST'])
def login():
    init_db()
    next_url = request.args.get('next') or url_for('index')
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        editor_user = os.environ.get('EDITOR_USER', 'editor')
        editor_pass = os.environ.get('EDITOR_PASS', 'password')
        if username == editor_user and password == editor_pass:
            session['editor_logged_in'] = True
            flash('Logged in as editor.', 'success')
            return redirect(next_url)
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html', next=next_url)


@app.route('/logout')
def logout():
    session.pop('editor_logged_in', None)
    flash('Logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/species/new', methods=['GET', 'POST'])
@editor_required
def new_species():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Species name cannot be empty.', 'warning')
            return redirect(url_for('new_species'))
        existing = Species.query.filter_by(name=name).first()
        if existing:
            flash('Species already exists.', 'info')
            return redirect(url_for('species_profile', species_id=existing.id))
        sp = Species(name=name)
        db.session.add(sp)
        db.session.commit()
        flash(f'Species "{name}" added.', 'success')
        return redirect(url_for('species_profile', species_id=sp.id))
    return render_template('new_species.html')


@app.route('/species/<int:species_id>/edit', methods=['GET', 'POST'])
@editor_required
def edit_species(species_id):
    sp = Species.query.get_or_404(species_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Species name cannot be empty.', 'warning')
            return redirect(url_for('edit_species', species_id=sp.id))
        sp.name = name
        db.session.commit()
        flash('Species updated.', 'success')
        return redirect(url_for('species_profile', species_id=sp.id))
    return render_template('edit_species.html', species=sp)


@app.route('/animals/<int:animal_id>/edit', methods=['GET', 'POST'])
@editor_required
def edit_animal(animal_id):
    a = Animal.query.get_or_404(animal_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Animal name cannot be empty.', 'warning')
            return redirect(url_for('edit_animal', animal_id=a.id))
        a.name = name
        db.session.commit()
        flash('Animal updated.', 'success')
        return redirect(url_for('species_profile', species_id=a.species_id))
    return render_template('edit_animal.html', animal=a)


@app.route('/species/<int:species_id>')
def species_profile(species_id):
    sp = Species.query.get_or_404(species_id)
    posts = Post.query.filter_by(species_id=sp.id).order_by(Post.timestamp.desc()).all()
    return render_template('species.html', species=sp, posts=posts)


@app.route('/species')
def species_list():
    init_db()
    species = Species.query.order_by(Species.name).all()
    return render_template('species_list.html', species=species)


@app.route('/post/new', methods=['GET', 'POST'])
@editor_required
def new_post():
    species_list = Species.query.order_by(Species.name).all()
    users = User.query.order_by(User.name).all()
    # allow pre-selecting a species via query string, e.g. /post/new?species_id=3
    selected_species_id = request.args.get('species_id')
    if request.method == 'POST':
        caption = request.form.get('caption', '').strip()
        # prefer an explicitly entered animal_name; otherwise use existing_animal select
        animal_name = request.form.get('animal_name', '').strip() or None
        existing_animal = request.form.get('existing_animal')
        if not animal_name and existing_animal:
            animal_name = existing_animal
        notes = request.form.get('notes', '').strip() or None
        species_id = request.form.get('species')
        user_id = request.form.get('user_id')
        image = request.files.get('image')

        if not caption or not species_id or not image:
            flash('Caption, species selection and image are required.', 'warning')
            return redirect(url_for('new_post'))

        try:
            species_id = int(species_id)
        except ValueError:
            flash('Invalid species selection.', 'danger')
            return redirect(url_for('new_post'))

        sp = Species.query.get(species_id)
        if not sp:
            flash('Selected species not found.', 'danger')
            return redirect(url_for('new_post'))

        filename = secure_filename(image.filename)
        if filename == '':
            flash('Invalid image filename.', 'danger')
            return redirect(url_for('new_post'))

        # make filename unique
        timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{timestamp_str}{ext}"
        dest = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(dest)

        # validate optional user
        if user_id:
            try:
                user_id_int = int(user_id)
                u = User.query.get(user_id_int)
                if not u:
                    flash('Selected user not found.', 'warning')
                    return redirect(url_for('new_post'))
            except ValueError:
                flash('Invalid user selection.', 'warning')
                return redirect(url_for('new_post'))
        else:
            user_id_int = None

        post = Post(
            caption=caption,
            animal_name=animal_name,
            notes=notes,
            image_filename=filename,
            species_id=sp.id,
            user_id=user_id_int,
        )
        db.session.add(post)
        db.session.commit()
        flash('Post created.', 'success')
        return redirect(url_for('species_profile', species_id=sp.id))

    return render_template('new_post.html', species_list=species_list, users=users, selected_species_id=selected_species_id)


@app.route('/users')
def users_list():
    init_db()
    users = User.query.order_by(User.name).all()
    return render_template('users.html', users=users)


@app.route('/users/new', methods=['GET', 'POST'])
@editor_required
def new_user():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        bio = request.form.get('bio', '').strip() or None
        if not name:
            flash('Name is required', 'warning')
            return redirect(url_for('new_user'))
        u = User(name=name, bio=bio)
        db.session.add(u)
        db.session.commit()
        flash('User created.', 'success')
        return redirect(url_for('users_list'))
    return render_template('new_user.html')


@app.route('/species/<int:species_id>/animals', methods=['GET'])
def list_animals_for_species(species_id):
    sp = Species.query.get_or_404(species_id)
    animals = [{'id': a.id, 'name': a.name} for a in sp.animals]
    from flask import jsonify
    return jsonify(animals)


@app.route('/species/<int:species_id>/animals/new', methods=['POST'])
@editor_required
def create_animal(species_id):
    sp = Species.query.get_or_404(species_id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Animal name cannot be empty.', 'warning')
        return redirect(url_for('species_profile', species_id=sp.id))
    # avoid duplicates per species
    existing = Animal.query.filter_by(species_id=sp.id, name=name).first()
    if existing:
        flash('Animal already exists for this species.', 'info')
        return redirect(url_for('species_profile', species_id=sp.id))
    a = Animal(name=name, species_id=sp.id)
    db.session.add(a)
    db.session.commit()
    flash(f'Animal "{name}" added to {sp.name}.', 'success')
    return redirect(url_for('species_profile', species_id=sp.id))


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@editor_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    # remove image file if exists
    try:
        if post.image_filename:
            path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
            if os.path.exists(path):
                os.remove(path)
    except Exception as e:
        app.logger.warning(f"Failed removing image for post {post_id}: {e}")

    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.', 'info')
    # redirect to species page if possible
    return redirect(url_for('index'))


@app.route('/species/<int:species_id>/delete', methods=['POST'])
@editor_required
def delete_species(species_id):
    sp = Species.query.get_or_404(species_id)
    # delete posts and their images
    posts = Post.query.filter_by(species_id=sp.id).all()
    for p in posts:
        try:
            if p.image_filename:
                path = os.path.join(app.config['UPLOAD_FOLDER'], p.image_filename)
                if os.path.exists(path):
                    os.remove(path)
        except Exception as e:
            app.logger.warning(f"Failed removing image for post {p.id}: {e}")
        db.session.delete(p)

    db.session.delete(sp)
    db.session.commit()
    flash('Species and its posts were deleted.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
