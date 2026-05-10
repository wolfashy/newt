from flask import Flask
def register_blueprints(app: Flask):
    from routes.chat import bp as chat_bp
    from routes.voice import bp as voice_bp
    from routes.files import bp as files_bp
    from routes.meta import bp as meta_bp
    app.register_blueprint(chat_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(meta_bp)
