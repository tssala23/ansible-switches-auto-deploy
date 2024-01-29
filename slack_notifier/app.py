import slack_notifier.notifier as notifier

app = notifier.create_app()

if __name__ == "__main__":
    app.run()