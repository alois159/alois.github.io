import hashlib
import random
import sqlite3
from flask import Flask, render_template_string, request, g, redirect, url_for, session
from flask_socketio import SocketIO, emit
from difflib import get_close_matches

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('chat.db')
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def create_users_table():
    with app.app_context():
        db = get_db()
        c = db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE,
                      password_hash TEXT,
                      is_admin INTEGER DEFAULT 0)''')
        db.commit()

def create_messages_table():
    with app.app_context():
        db = get_db()
        c = db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sender TEXT,
                      receiver TEXT,
                      message TEXT)''')
        db.commit()

def init_database():
    create_users_table()
    create_messages_table()

init_database()

@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    c = db.cursor()

    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        message = request.form.get('message')
        sender = session['username']
        receiver = request.form.get('receiver')

        if message.strip() != '':
            if receiver != 'all':
                c.execute("INSERT INTO messages (sender, receiver, message) VALUES (?, ?, ?)", (sender, receiver, message))
            else:
                c.execute("INSERT INTO messages (sender, receiver, message) VALUES (?, ?, ?)", (sender, 'all', message))
            db.commit()

            socketio.emit('message', {'username': sender, 'message': message, 'admin': session.get('is_admin', False), 'receiver': receiver}, broadcast=True)

        return '', 204
    else:
        c.execute("SELECT DISTINCT username FROM users")
        users = [row[0] for row in c.fetchall()]
        c.execute("SELECT sender, message FROM messages WHERE receiver='all' OR receiver=?", (session['username'],))
        messages = c.fetchall()
        return render_template_string("""
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Chat</title>
                <style>
                    body {
                        background-color: #282c34;
                        font-family: 'Roboto', sans-serif;
                        color: white;
                        margin: 0;
                        padding: 0;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                    }
                    .header {
                        width: 100%;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        padding: 10px 20px;
                        background-color: #1c1e22;
                        position: fixed;
                        top: 0;
                        z-index: 1000;
                    }
                    .header a {
                        color: white;
                        text-decoration: none;
                        padding: 5px 10px;
                        border: 1px solid transparent;
                        border-radius: 5px;
                    }
                    .header a:hover {
                        background-color: rgba(255, 255, 255, 0.1);
                    }
                    .chat-container {
                        background-color: #3c4048;
                        border-radius: 10px;
                        box-shadow: 0px 0px 10px 0px rgba(0, 0, 0, 0.1);
                        margin: 80px 20px;
                        max-width: 800px;
                        width: 100%;
                        padding: 20px;
                    }
                    .message-input {
                        border-radius: 5px;
                        border: 1px solid #ccc;
                        font-size: 16px;
                        margin-bottom: 10px;
                        padding: 10px;
                        width: calc(100% - 20px);
                    }
                    .send-button {
                        background-color: #4caf50;
                        border: none;
                        border-radius: 5px;
                        color: white;
                        cursor: pointer;
                        font-size: 16px;
                        padding: 10px 20px;
                        margin-left: 10px;
                    }
                    .send-button:hover {
                        background-color: #45a049;
                    }
                    .message {
                        background-color: #525760;
                        border-radius: 5px;
                        margin-bottom: 5px;
                        padding: 10px;
                    }
                    .username {
                        font-weight: bold;
                    }
                    .content {
                        margin-left: 5px;
                    }
                    .admin-message {
                        color: #f00;
                    }
                    .admin-controls {
                        position: fixed;
                        top: 50px;
                        right: 20px;
                        padding: 10px
                        background-color: #1c1e22;
                        border-radius: 5px;
                        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                        z-index: 1000;
                    }
                    .admin-command-input {
                        border: none;
                        border-radius: 3px;
                        padding: 8px;
                        margin-right: 5px;
                        font-size: 14px;
                        width: 200px;
                    }
                    .admin-command-button {
                        background-color: #4caf50;
                        border: none;
                        border-radius: 3px;
                        color: white;
                        cursor: pointer;
                        font-size: 14px;
                        padding: 8px 12px;
                    }
                    .admin-command-button:hover {
                        background-color: #45a049;
                    }
                    .delete-button {
                        background-color: #ff0000;
                        border: none;
                        border-radius: 3px;
                        color: white;
                        cursor: pointer;
                        font-size: 14px;
                        padding: 8px 12px;
                    }
                    .delete-button:hover {
                        background-color: #c00000;
                    }
                </style>
            </head>
            <body>
                <div class="header">
                    <div></div>
                    <div>
                        <span>Welcome, {{ session.username }}</span>
                        <a href="/logout">Logout</a>
                        <a href="/mp">MP</a>
                    </div>
                </div>
                {% if session.get('is_admin') %}
                <div class="admin-controls">
                    <input id="admin-command-input" class="admin-command-input" placeholder="Enter command...">
                    <button id="admin-command-button" class="admin-command-button" onclick="sendAdminCommand()">Send</button>
                </div>
                {% endif %}
                <div class="chat-container">
                    <div id="chat-messages" class="chat-messages">
                        {% for sender, message in messages %}
                        <div class="message">
                            <span class="username">{{ sender }}: </span>
                            <span class="content">{{ message }}</span>
                        </div>
                        {% endfor %}
                    </div>
                    <form id="message-form" method="post">
                        <input id="receiver" type="hidden" name="receiver" value="all">
                        <input id="message-input" class="message-input" name="message" placeholder="Type your message...">
                        <button id="send-button" class="send-button" type="submit">Send</button>
                    </form>
                </div>

                <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.3.2/socket.io.js"></script>
                <script>
                    var socket = io.connect();

                    document.getElementById('message-form').addEventListener('submit', function(event) {
                        event.preventDefault();
                        var messageInput = document.getElementById('message-input');
                        var message = messageInput.value;
                        var receiver = document.getElementById('receiver').value;
                        messageInput.value = '';
                        sendMessage(message, receiver);
                    });

                    function sendMessage(message, receiver) {
                        if (message.trim() === '') {
                            return;
                        }

                        var messageElement = document.createElement('div');
                        messageElement.classList.add('message');
                        var usernameSpan = document.createElement('span');
                        usernameSpan.classList.add('username');
                        usernameSpan.textContent = '{{ session.username }}: ';
                        messageElement.appendChild(usernameSpan);
                        var contentSpan = document.createElement('span');
                        contentSpan.classList.add('content');
                        contentSpan.textContent = message;
                        messageElement.appendChild(contentSpan);
                        document.getElementById('chat-messages').appendChild(messageElement);

                        socket.emit('message', {'message': message, 'receiver': receiver});
                    }

                    socket.on('message', function(data) {
                        var messageElement = document.createElement('div');
                        messageElement.classList.add('message');
                        var usernameSpan = document.createElement('span');
                        usernameSpan.classList.add('username');
                        usernameSpan.textContent = data.username + ': ';
                        messageElement.appendChild(usernameSpan);
                        var contentSpan = document.createElement('span');
                        contentSpan.classList.add('content');
                        contentSpan.textContent = data.message;
                        messageElement.appendChild(contentSpan);
                        document.getElementById('chat-messages').appendChild(messageElement);
                    });

                    function sendAdminCommand() {
                        var commandInput = document.getElementById('admin-command-input');
                        var command = commandInput.value;
                        commandInput.value = '';
                        socket.emit('admin_command', {'command': command});
                    }
                </script>
            </body>
            </html>
        """, users=users, messages=messages)

@app.route('/login', methods=['GET', 'POST'])
def login():
    db = get_db()
    c = db.cursor()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        c.execute("SELECT * FROM users WHERE username=? AND password_hash=?", (username, password_hash))
        user = c.fetchone()

        if user:
            session['username'] = username
            session['is_admin'] = bool(user[3])
            return redirect(url_for('index'))
        else:
            return "Invalid credentials", 401

    return render_template_string("""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Login</title>
            <style>
                body {
                    background-color: #282c34;
                    font-family: 'Roboto', sans-serif;
                    color: white;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .login-container {
                    background-color: #3c4048;
                    border-radius: 10px;
                    box-shadow: 0px 0px 10px 0px rgba(0, 0, 0, 0.1);
                    max-width: 400px;
                    width: 100%;
                    padding: 20px;
                    text-align: center;
                }
                .login-input {
                    border-radius: 5px;
                    border: 1px solid #ccc;
                    font-size: 16px;
                    margin-bottom: 10px;
                    padding: 10px;
                    width: calc(100% - 20px);
                }
                .login-button {
                    background-color: #4caf50;
                    border: none;
                    border-radius: 5px;
                    color: white;
                    cursor: pointer;
                    font-size: 16px;
                    padding: 10px 20px;
                    width: 100%;
                }
                .login-button:hover {
                    background-color: #45a049;
                }
                .register-link {
                    color: #61dafb;
                    display: block;
                    margin-top: 20px;
                    text-decoration: none;
                }
                .register-link:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <div class="login-container">
                <h2>Login</h2>
                <form method="post">
                    <input class="login-input" type="text" name="username" placeholder="Username" required>
                    <input class="login-input" type="password" name="password" placeholder="Password" required>
                    <button class="login-button" type="submit">Login</button>
                </form>
                <a class="register-link" href="/register">Register</a>
            </div>
        </body>
        </html>
    """)

@app.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db()
    c = db.cursor()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
            db.commit()
        except sqlite3.IntegrityError:
            return "Username already exists", 400

        session['username'] = username
        session['is_admin'] = False
        return redirect(url_for('index'))

    return render_template_string("""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Register</title>
            <style>
                body {
                    background-color: #282c34;
                    font-family: 'Roboto', sans-serif;
                    color: white;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .register-container {
                    background-color: #3c4048;
                    border-radius: 10px;
                    box-shadow: 0px 0px 10px 0px rgba(0, 0, 0, 0.1);
                    max-width: 400px;
                    width: 100%;
                    padding: 20px;
                    text-align: center;
                }
                .register-input {
                    border-radius: 5px;
                    border: 1px solid #ccc;
                    font-size: 16px;
                    margin-bottom: 10px;
                    padding: 10px;
                    width: calc(100% - 20px);
                }
                .register-button {
                    background-color: #4caf50;
                    border: none;
                    border-radius: 5px;
                    color: white;
                    cursor: pointer;
                    font-size: 16px;
                    padding: 10px 20px;
                    width: 100%;
                }
                .register-button:hover {
                    background-color: #45a049;
                }
                .login-link {
                    color: #61dafb;
                    display: block;
                    margin-top: 20px;
                    text-decoration: none;
                }
                .login-link:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <div class="register-container">
                <h2>Register</h2>
                <form method="post">
                    <input class="register-input" type="text" name="username" placeholder="Username" required>
                    <input class="register-input" type="password" name="password" placeholder="Password" required>
                    <button class="register-button" type="submit">Register</button>
                </form>
                <a class="login-link" href="/login">Login</a>
            </div>
        </body>
        </html>
    """)

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('is_admin', None)
    return redirect(url_for('login'))

@app.route('/mp', methods=['GET', 'POST'])
def mp():
    db = get_db()
    c = db.cursor()

    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        search_query = request.form.get('search_query')
        c.execute("SELECT username FROM users")
        users = [row[0] for row in c.fetchall()]

        matched_users = get_close_matches(search_query, users, n=5, cutoff=0.8)
        return render_template_string("""
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Search Users</title>
                <style>
                    body {
                        background-color: #282c34;
                        font-family: 'Roboto', sans-serif;
                        color: white;
                        margin: 0;
                        padding: 0;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                    }
                    .search-container {
                        background-color: #3c4048;
                        border-radius: 10px;
                        box-shadow: 0px 0px 10px 0px rgba(0, 0, 0, 0.1);
                        max-width: 400px;
                        width: 100%;
                        padding: 20px;
                        text-align: center;
                    }
                    .search-input {
                        border-radius: 5px;
                        border: 1px solid #ccc;
                        font-size: 16px;
                        margin-bottom: 10px;
                        padding: 10px;
                        width: calc(100% - 20px);
                    }
                    .search-button {
                        background-color: #4caf50;
                        border: none;
                        border-radius: 5px;
                        color: white;
                        cursor: pointer;
                        font-size: 16px;
                        padding: 10px 20px;
                        width: 100%;
                    }
                    .search-button:hover {
                        background-color: #45a049;
                    }
                    .user-list {
                        list-style: none;
                        padding: 0;
                        margin: 0;
                    }
                    .user-item {
                        background-color: #525760;
                        border-radius: 5px;
                        margin-bottom: 10px;
                        padding: 10px;
                    }
                    .user-link {
                        color: white;
                        text-decoration: none;
                    }
                    .user-link:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <div class="search-container">
                    <h2>Search Users</h2>
                    <form method="post">
                        <input class="search-input" type="text" name="search_query" placeholder="Search users..." required>
                        <button class="search-button" type="submit">Search</button>
                    </form>
                    <ul class="user-list">
                        {% for user in matched_users %}
                        <li class="user-item">
                            <a class="user-link" href="{{ url_for('mp_chat', username=user) }}">{{ user }}</a>
                        </li>
                        {% endfor %}
                    </ul>
                </div>
            </body>
            </html>
        """, matched_users=matched_users)

    return render_template_string("""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Search Users</title>
            <style>
                body {
                    background-color: #282c34;
                    font-family: 'Roboto', sans-serif;
                    color: white;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .search-container {
                    background-color: #3c4048;
                    border-radius: 10px;
                    box-shadow: 0px 0px 10px 0px rgba(0, 0, 0, 0.1);
                    max-width: 400px;
                    width: 100%;
                    padding: 20px;
                    text-align: center;
                }
                .search-input {
                    border-radius: 5px;
                    border: 1px solid #ccc;
                    font-size: 16px;
                    margin-bottom: 10px;
                    padding: 10px;
                    width: calc(100% - 20px);
                }
                .search-button {
                    background-color: #4caf50;
                    border: none;
                    border-radius: 5px;
                    color: white;
                    cursor: pointer;
                    font-size: 16px;
                    padding: 10px 20px;
                    width: 100%;
                }
                .search-button:hover {
                    background-color: #45a049;
                }
            </style>
        </head>
        <body>
            <div class="search-container">
                <h2>Search Users</h2>
                <form method="post">
                    <input class="search-input" type="text" name="search_query" placeholder="Search users..." required>
                    <button class="search-button" type="submit">Search</button>
                </form>
            </div>
        </body>
        </html>
    """)

@app.route('/mp/<username>', methods=['GET', 'POST'])
def mp_chat(username):
    db = get_db()
    c = db.cursor()

    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        message = request.form.get('message')
        sender = session['username']

        if message.strip() != '':
            c.execute("INSERT INTO messages (sender, receiver, message) VALUES (?, ?, ?)", (sender, username, message))
            db.commit()

            socketio.emit('message', {'username': sender, 'message': message, 'receiver': username}, broadcast=True)

        return '', 204
    else:
        c.execute("SELECT sender, message FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)",
                  (session['username'], username, username, session['username']))
        messages = c.fetchall()
        return render_template_string("""
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>MP with {{ username }}</title>
                <style>
                    body {
                        background-color: #282c34;
                        font-family: 'Roboto', sans-serif;
                        color: white;
                        margin: 0;
                        padding: 0;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                    }
                    .chat-container {
                        background-color: #3c4048;
                        border-radius: 10px;
                        box-shadow: 0px 0px 10px 0px rgba(0, 0, 0, 0.1);
                        margin: 80px 20px;
                        max-width: 800px;
                        width: 100%;
                        padding: 20px;
                    }
                    .message-input {
                        border-radius: 5px;
                        border: 1px solid #ccc;
                        font-size: 16px;
                        margin-bottom: 10px;
                        padding: 10px;
                        width: calc(100% - 20px);
                    }
                    .send-button {
                        background-color: #4caf50;
                        border: none;
                        border-radius: 5px;
                        color: white;
                        cursor: pointer;
                        font-size: 16px;
                        padding: 10px 20px;
                        margin-left: 10px;
                    }
                    .send-button:hover {
                        background-color: #45a049;
                    }
                    .message {
                        background-color: #525760;
                        border-radius: 5px;
                        margin-bottom: 5px;
                        padding: 10px;
                    }
                    .username {
                        font-weight: bold;
                    }
                    .content {
                        margin-left: 5px;
                    }
                </style>
            </head>
            <body>
                <div class="chat-container">
                    <h2>Chat with {{ username }}</h2>
                    <div id="chat-messages" class="chat-messages">
                        {% for sender, message in messages %}
                        <div class="message">
                            <span class="username">{{ sender }}: </span>
                            <span class="content">{{ message }}</span>
                        </div>
                        {% endfor %}
                    </div>
                    <form id="message-form" method="post">
                        <input id="receiver" type="hidden" name="receiver" value="{{ username }}">
                        <input id="message-input" class="message-input" name="message" placeholder="Type your message...">
                        <button id="send-button" class="send-button" type="submit">Send</button>
                    </form>
                </div>

                <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.3.2/socket.io.js"></script>
                <script>
                    var socket = io.connect();

                    document.getElementById('message-form').addEventListener('submit', function(event) {
                        event.preventDefault();
                        var messageInput = document.getElementById('message-input');
                        var message = messageInput.value;
                        var receiver = document.getElementById('receiver').value;
                        messageInput.value = '';
                        sendMessage(message, receiver);
                    });

                    function sendMessage(message, receiver) {
                        if (message.trim() === '') {
                            return;
                        }

                        var messageElement = document.createElement('div');
                        messageElement.classList.add('message');
                        var usernameSpan = document.createElement('span');
                        usernameSpan.classList.add('username');
                        usernameSpan.textContent = '{{ session.username }}: ';
                        messageElement.appendChild(usernameSpan);
                        var contentSpan = document.createElement('span');
                        contentSpan.classList.add('content');
                        contentSpan.textContent = message;
                        messageElement.appendChild(contentSpan);
                        document.getElementById('chat-messages').appendChild(messageElement);

                        socket.emit('message', {'message': message, 'receiver': receiver});
                    }

                    socket.on('message', function(data) {
                        if (data.receiver === '{{ username }}' || data.username === '{{ username }}' || data.receiver === '{{ session.username }}') {
                            var messageElement = document.createElement('div');
                            messageElement.classList.add('message');
                            var usernameSpan = document.createElement('span');
                            usernameSpan.classList.add('username');
                            usernameSpan.textContent = data.username + ': ';
                            messageElement.appendChild(usernameSpan);
                            var contentSpan = document.createElement('span');
                            contentSpan.classList.add('content');
                            contentSpan.textContent = data.message;
                            messageElement.appendChild(contentSpan);
                            document.getElementById('chat-messages').appendChild(messageElement);
                        }
                    });
                </script>
            </body>
            </html>
        """, username=username, messages=messages)

if __name__ == '__main__':
    socketio.run(app, debug=True)
