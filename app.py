import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# 1. CONFIGURATION
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def get_db_uri():
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        if os.getenv('VERCEL'):
            return f"sqlite:///{os.path.join('/tmp', 'database.db')}"
        return f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_fallback_secret_key_12345')
    SQLALCHEMY_DATABASE_URI = get_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    
    if os.getenv('VERCEL'):
        UPLOAD_FOLDER = '/tmp/uploads'
        PDF_UPLOAD_FOLDER = '/tmp/uploads/pdfs'
        COVER_UPLOAD_FOLDER = '/tmp/static/images/covers'
        AUDIO_FOLDER = '/tmp/static/audio'
    else:
        UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'uploads')
        PDF_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'pdfs')
        COVER_UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'images', 'covers')
        AUDIO_FOLDER = os.path.join(STATIC_FOLDER, 'audio')

# ==========================================
# 2. DATABASE MODELS FOR FRONTEND RENDERING
# ==========================================
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True, default='covers/default.jpg')
    pdf_file = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    category = db.relationship('Category', lazy=True)
    chapters = db.relationship('Chapter', backref='book', lazy=True)

class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    text_content = db.Column(db.Text, nullable=False)

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    book = db.relationship('Book', lazy=True)

class ReadingHistory(db.Model):
    __tablename__ = 'reading_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    last_chapter_number = db.Column(db.Integer, default=1)
    book = db.relationship('Book', lazy=True)

# ==========================================
# 3. FRONTEND APP & ROUTES
# ==========================================
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    try:
        os.makedirs(Config.PDF_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.COVER_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.AUDIO_FOLDER, exist_ok=True)
    except Exception:
        pass

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_global_vars():
        try:
            categories = Category.query.all()
        except Exception:
            categories = []
        return {
            'all_categories': categories,
            'elevenlabs_configured': True
        }

    @app.route('/')
    def index():
        try:
            all_books = Book.query.order_by(Book.id.asc()).all()
            categories = Category.query.all()
        except Exception:
            all_books = []
            categories = []
        shelf1_books = all_books[0:5] if len(all_books) >= 5 else all_books
        shelf2_books = all_books[5:10] if len(all_books) >= 10 else []
        shelf3_books = all_books[10:15] if len(all_books) >= 15 else []
        return render_template('index.html', shelf1_books=shelf1_books, shelf2_books=shelf2_books, shelf3_books=shelf3_books, all_books=all_books, categories=categories)

    @app.route('/books')
    def books_catalog():
        try:
            all_books = Book.query.all()
            categories = Category.query.all()
        except Exception:
            all_books = []
            categories = []
        return render_template('books.html', books=all_books, categories=categories)

    @app.route('/book/<int:book_id>')
    def book_detail(book_id):
        book = Book.query.get(book_id)
        if not book:
            return redirect(url_for('books_catalog'))
        return render_template('book_detail.html', book=book)

    @app.route('/reader/<int:book_id>')
    def reader(book_id):
        book = Book.query.get(book_id)
        if not book:
            return redirect(url_for('books_catalog'))
        chapter_id = request.args.get('chapter', 1, type=int)
        current_chapter = Chapter.query.filter_by(book_id=book_id, chapter_number=chapter_id).first()
        if not current_chapter and book.chapters:
            current_chapter = book.chapters[0]
        return render_template('reader.html', book=book, current_chapter=current_chapter)

    @app.route('/audio-player/<int:book_id>')
    def audio_player(book_id):
        book = Book.query.get(book_id)
        if not book:
            return redirect(url_for('books_catalog'))
        chapter_id = request.args.get('chapter', 1, type=int)
        current_chapter = Chapter.query.filter_by(book_id=book_id, chapter_number=chapter_id).first()
        if not current_chapter and book.chapters:
            current_chapter = book.chapters[0]
        return render_template('audio_player.html', book=book, current_chapter=current_chapter)

    @app.route('/favorites')
    def favorites():
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        try:
            favs = Favorite.query.filter_by(user_id=current_user.id).all()
        except Exception:
            favs = []
        return render_template('favorites.html', favorites=favs)

    @app.route('/history')
    def history():
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        try:
            hist = ReadingHistory.query.filter_by(user_id=current_user.id).all()
        except Exception:
            hist = []
        return render_template('history.html', history=hist)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('index'))
            flash("Invalid email or password", "danger")
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            if User.query.filter_by(email=email).first():
                flash("Email already registered", "danger")
            else:
                user = User(username=username, email=email, password_hash=generate_password_hash(password))
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return redirect(url_for('index'))
        return render_template('register.html')

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/admin')
    def admin_dashboard():
        try:
            books = Book.query.all()
        except Exception:
            books = []
        return render_template('admin/dashboard.html', books=books)

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
