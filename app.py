# note that this finance will not run properly now as lookupfunction wont work as api key expired
# importing packages
import os

import sqlite3
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, convert_listoftuple_to_listofdicts, convert_listoftuple_to_listofdictsprint

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure  use SQLite database
conn = sqlite3.connect('finance.db', check_same_thread=False)
c = conn.cursor()

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    id = session["user_id"]
    nameofuserdict = c.execute("SELECT username FROM users WHERE id = ?", (id,))
    keylist = ["username"]
    nameofuserdict = convert_listoftuple_to_listofdicts(keylist, c)
    nameofuser = nameofuserdict[0]["username"]

    # get cashbalance
    cashbalancedict = c.execute("SELECT cash FROM users WHERE username= ?", (nameofuser,))
    keylist = ["cash"]
    cashbalancedict = convert_listoftuple_to_listofdicts(keylist, c)
    cashbalance = cashbalancedict[0]["cash"]

    # get list of dict of all stocks grouped together owned by specific
    # stocksowneddict = db.execute("SELECT symbol, symbolname, SUM(qtybought) AS qtybought FROM purchases WHERE id=? GROUP BY symbol", id) ? this was orignal way but changed to below to not show case when sum is 0 because employed + and - qty methodology
    stocksowneddict = c.execute("SELECT symbol, qtybought FROM ( SELECT symbol, symbolname, SUM(qtybought) AS qtybought FROM purchases WHERE id=? GROUP BY symbol) WHERE qtybought > 0", (id,))
    keylist = ["symbol", "qtybought"]
    stocksowneddict = convert_listoftuple_to_listofdicts(keylist, c)
    
    # created temp dicts which is intialized everytime main page is called
    # tempprice dict for current stock prices amd tempsymbol value for the total price per stock by multipyign current price and qty prucahsed
    temppricedict = {}
    tempsymbolvalue = {}
    for stocks in stocksowneddict:
        temppricedict[stocks["symbol"]] = lookup(stocks["symbol"])["price"]
        tempsymbolvalue[stocks["symbol"]] = lookup(stocks["symbol"])["price"] * stocks["qtybought"]

    # total value of portfolio
    total = cashbalance
    for symbolandvalue in tempsymbolvalue:
        total += tempsymbolvalue[symbolandvalue]

    # render template html passing in cash, stocckownedict and temppricedict, tempsymbolvalue
    return render_template("index.html", cash=cashbalance, stocksdetails=stocksowneddict, tempprice=temppricedict, stockvaluebysymbol = tempsymbolvalue, totalvalue = total)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # if request method by get return buy.html
    if request.method == "GET":
        return render_template("buy.html")

    # if request method by POST buy a stock
    # if symbol is blank return apology
    if not request.form.get("symbol"):
        return apology("missing symbol", 400)

    # if shares number is blank return apology
    if not request.form.get("shares"):
        return apology("missing shares", 400)

    # if there is input but the stock does not exists return error
    if not lookup(request.form.get("symbol")):
        return apology("invalid symbol", 400)

    # need to validate client side input for shares to return apology for fractional, negative and non-numeric
    # check if numeric if not return apology
    if not request.form.get("shares").isnumeric():
        return apology("key in numeric", 400)

    # check if positive if not return apology
    if int(request.form.get("shares")) < 0:
        return apology("key in positive number", 400)

    # check if whole number is not return apology
    if not request.form.get("shares").isdigit():
        return apology("key in whole number", 400)

    # populate new database table based on session ID
    # first check if have enough money to buy the requested qty of stock
    symboldict = lookup(request.form.get("symbol"))
    symbolshares = request.form.get("shares")

    # query current cash balance
    # query username than use username to search for cash balance as username is indexed
    id = session["user_id"]
    nameofuserdict = c.execute("SELECT username FROM users WHERE id = ?", (id,))
    keylist = ["username"]
    nameofuserdict = convert_listoftuple_to_listofdicts(keylist, c)
    # remember db.execute returns a list of dict
    nameofuser = nameofuserdict[0]["username"]
    cashbalancedict = c.execute("SELECT cash FROM users WHERE username= ?", (nameofuser,))
    keylist = ["cash"]
    cashbalancedict = convert_listoftuple_to_listofdicts(keylist, c)
    cashbalance = cashbalancedict[0]["cash"]

    #  check if price x qty more than cash balance render aplology
    if (symboldict["price"] * float(symbolshares)) > cashbalance:
        return apology("cant afford", 400)

    #  else if within cash balance purchase it updating the database for purchases and reducing cash balance in users
    c.execute("INSERT INTO purchases (id, symbol, symbolname, pricebought, qtybought, dateoftransaction) VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))", (id, symboldict["symbol"], symboldict["name"], symboldict["price"], symbolshares))
    conn.commit()

    # reduce cash balance in users table due to purchase by updating
    newcashbalance = cashbalance - (symboldict["price"] * float(symbolshares))
    c.execute("UPDATE users SET cash = ? WHERE username = ?", (newcashbalance, nameofuser))
    conn.commit()

    # redirect user to homepage once data validated and stored
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    id = session["user_id"]
    historydict = c.execute("SELECT symbol, qtybought, pricebought, dateoftransaction FROM purchases WHERE id=? ORDER BY dateoftransaction", (id,))
    keylist = ["symbol", "qtybought", "pricebought", "dateoftransaction"]
    historydict = convert_listoftuple_to_listofdicts(keylist, c)
    return render_template("history.html", historydict=historydict)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = c.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
        keylist = list(head[0] for head in c.description)
        rows = convert_listoftuple_to_listofdicts(keylist, c)


        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # if by GET returns querying stock symbol to be inputted
    if request.method == "GET":
        return render_template("quote.html")

    #  else if by POST once sumbit stock renders the quoted stock prices
    # if not symbol input return error
    if not request.form.get("symbol"):
        return apology("missing symbol", 400)

    # if there is input but the stock does not exists return error
    if not lookup(request.form.get("symbol")):
        return apology("invalid symbol", 400)

    # if there is valid input utilise lookup function and return embbeded value to quoted html, stored in dict
    symboldict = lookup(request.form.get("symbol"))
    return render_template("quoted.html", name=symboldict["name"], price=symboldict["price"], symbol=symboldict["symbol"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # return apology("TOdo")
    if request.method == "GET":
        return render_template("register.html")

    # if request method is post
    # require username render apology if blank
    if not request.form.get("username"):
        return apology("must provide username", 400)

    # require username render apology if username already exists
    rows = c.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
    keylist = list(head[0] for head in c.description)
    rows = convert_listoftuple_to_listofdicts(keylist, c)
    if len(rows) != 0:
        return apology("Username is not available", 400)

    # require password render apology if blank
    if not request.form.get("password"):
        return apology("must provide password", 400)

    # client side verification not enuf need server side require password to have 5 characters minimal, min one uppercase alpha, min one lower case alpha, min one number
    #  check client input password if at least 5 chars logn if not render apology
    if len(request.form.get("password")) < 5:
        return apology("password must be 5 characters long", 400)

    # check client input password if at least one uppercase alpha
    if not any(char.isupper() for char in request.form.get("password")):
        return apology("password must have one uppercase alpha", 400)

    # check client input password if at least one lowercase alpha
    if not any(char.islower() for char in request.form.get("password")):
        return apology("password must have one lowercase alpha", 400)

    # check client input password if at least one number
    if not any(char.isdigit() for char in request.form.get("password")):
        return apology("password must have one number", 400)

    # check client input password if at least one special character and if character in list specified
    def tempfunction(password):
        for char in password:
            # if char found to be in list we return meanign break out of function and continue normally
            if char in "!@#$%^&*_=+":
                return 1
            # if current char not in list go to next iteration of the loop
            elif char not in "!@#$%^&*_=+":
                continue
        # if dinnt return earlier means special char approved doesnt exist so return apology
        return 0

    # using a function here so that i can put the return outside, if in main code rest fo program wont run
    # had to use 0 and 1 and if outside to check the function because if i put the return apology inside the temp function it returns from the function back to main an djust cointues, i need a rteurn to live in the main
    if not tempfunction(request.form.get("password")):
        return apology("password must have one approved special character", 400)

    # ensure password confirmation is same as password field render apology if not
    if request.form.get("password") != request.form.get("confirmation"):
        return apology("passwords dont match", 400)

    # hash the password and insert the new user and password into users table in finance.db
    c.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (request.form.get("username"), generate_password_hash(request.form.get("password"))))
    conn.commit()

    # redirect route to / after successfull registration
    return redirect("/login")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":

        # if by get render sell.html with appropriate values
        # identify current user
        id = session["user_id"]

        # get list of dict of all stocks grouped together owned by specific
        # stocksowneddict = db.execute("SELECT symbol, SUM(qtybought) AS qtybought FROM purchases WHERE id=? GROUP BY symbol", id)
        stocksowneddict = c.execute("SELECT symbol, qtybought FROM ( SELECT symbol, symbolname, SUM(qtybought) AS qtybought FROM purchases WHERE id=? GROUP BY symbol) WHERE qtybought > 0", (id,))
        keylist = ["symbol", "qtybought"]
        stocksowneddict = convert_listoftuple_to_listofdicts(keylist, c)

        # once data is retrived on what stocks are owned for the user render template
        return render_template("sell.html", stocksowneddict=stocksowneddict)

    # else if method is post, sell the stock, update databses including cash and do checks then return to main page at end
    # if user fails to select a stock render apology
    if not request.form.get("symbol"):
        return apology("missing symbol", 400)

    # if usersomehow submits a stock they dont own (like they manually change the client code), essentialy server side verfication of client side input
    id = session["user_id"]
    # stocksowneddict = db.execute("SELECT symbol, SUM(qtybought) AS qtybought FROM purchases WHERE id=? GROUP BY symbol", id)
    stocksowneddict = c.execute("SELECT symbol, qtybought FROM ( SELECT symbol, symbolname, SUM(qtybought) AS qtybought FROM purchases WHERE id=? GROUP BY symbol) WHERE qtybought > 0", (id,))
    keylist = ["symbol", "qtybought"]
    stocksowneddict = convert_listoftuple_to_listofdicts(keylist, c)

    tempstockslist = []
    for tempstocks in stocksowneddict:
        tempstockslist.append(tempstocks["symbol"])

    if request.form.get("symbol") not in tempstockslist:
        return apology("symbol not owned", 400)

    # if user leaves number of shares field blank render a apology
    if not request.form.get("shares"):
        return apology("missing shares", 400)

    # if user tries to sell more than the number fo that stocks he owns (no short sellign in this case)
    for shares in stocksowneddict:
        if request.form.get("symbol") == shares["symbol"]:
            if int(request.form.get("shares")) > shares["qtybought"]:
                return apology("missing shares", 400)

    # if all the above checks have been cleared then update databases, 1. update users database cash, 2. update purchases database
    #  identify user name as indexed faster query
    nameofuserdict = c.execute("SELECT username FROM users WHERE id = ?", (id,))
    keylist = ["username"]
    nameofuserdict = convert_listoftuple_to_listofdicts(keylist, c)
    nameofuser = nameofuserdict[0]["username"]

    # inqure current cash balance of username
    cashbalancedict = c.execute("SELECT cash FROM users WHERE username= ?", (nameofuser,))
    keylist = ["cash"]
    cashbalancedict = convert_listoftuple_to_listofdicts(keylist, c)
    cashbalance = cashbalancedict[0]["cash"]

    #  Update cash balance by increasing based on number of shares sold
    symboldict = lookup(request.form.get("symbol"))
    symbolshares = request.form.get("shares")
    newcashbalance = cashbalance + (symboldict["price"] * float(symbolshares))
    c.execute("UPDATE users SET cash = ? WHERE username = ?", (newcashbalance, nameofuser))
    conn.commit()

    #  Reduce sum qty bought in purchases by inserting negative qty values, so when query runs it holds logically
    negativesymbolshares = - int(symbolshares)
    c.execute("INSERT INTO purchases (id, symbol, symbolname, pricebought, qtybought, dateoftransaction) VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))", (id, symboldict["symbol"], symboldict["name"], symboldict["price"], negativesymbolshares))
    conn.commit()
    # return redirect to homepage
    return redirect("/")
