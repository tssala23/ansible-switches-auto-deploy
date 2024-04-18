# ansible-switches-auto-deploy
Automated deployment of MOC/OCT switches on commit to ansible-switches repo

## Configuration

This application can be configured using the following environment variables:

- `FLASK_AUTODEPLOY_WEBHOOKURL` -- this is the URL to which we will send the slack notification
- `FLASK_AUTODEPLOY_REPOURL` -- the URL for the ansible project we will run when we receive a change notification from GitHub
- `FLASK_AUTODEPLOY_PLAYBOOK` -- we will run this playbook contained in the `FLASK_AUTODEPLOY_REPOSITORY`

## Running the code locally

You can run the code locally by installing the requirements into a Python virtual environment. For example:

```
python -m venv .venv
.venv/bin/activate
pip install -r requirements.txt
```

Place your desired configuration into a `.env` file. For development, you may want to point at an alternate ansible project and use something like [postbin](https://www.toptal.com/developers/postbin/) to receive the notification and verify the contents (the postbin URL presented here is just an example; you would need to allocate your own):

```
FLASK_AUTODEPLOY_REPOURL=https://github.com/larsks/ansible-switches-fake
FLASK_AUTODEPLOY_WEBHOOKURL=https://www.toptal.com/developers/postbin/1702338557648-3463392409030
```

Flask will automatically load this configuration when you run the app using the `flask` command line tool:

```
flask --app app:app run
```

## Running the tests

To run the tests, first install the test requirements into your virtual environment:

```
pip install -r test-requirements.txt
```

Then use the `pytest` command to run the tests:

```
pytest --cov=app --cov-report=html
```

The above command will run the tests contained in `test_app.py` and will produce a coverage report in `htmlcov/index.html`.

## Running in a container

### Building a container image

You can build a containerized version of this application using the included `Dockerfile`. Using Podman:

```
podman build -t ansible-switches-autodeploy .
```

### Running the container

You can configure the container using the settings in your `.env` file by using the `--env-file` option to `podman run`:

```
podman run --env-file .env -p 8000:8000 ansible-switches-autodeploy
```

This will expose the web service on local port `8000`.

## TODO

- This code assumes that the directory in which it is running is writable. This may not be true, particularly when running under OpenShift. The application should accept a configuration value that identifies a writable working directory and should use that directory for all file operations.
