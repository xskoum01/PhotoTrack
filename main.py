from flask import Flask, render_template

app = Flask(__name__)

@app.route('/configuration')
def configuration():
    return render_template('configuration.html')

if __name__ == '__main__':
    app.run()
