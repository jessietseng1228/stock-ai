print("🔥 APP FILE IS RUNNING")

from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    print("🔥 REQUEST HIT")
    return "OK"

if __name__ == "__main__":
    print("🔥 MAIN STARTED")
    app.run(host="0.0.0.0", port=10000)