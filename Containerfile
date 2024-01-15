FROM registry.access.redhat.com/ubi8/python-39@sha256:496f9eee1837022e749a5f2d5c9ae91720200e03c38528894aee4eb6b3bb78b5

COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY app.py ./

CMD [ "gunicorn", "-b", "0.0.0.0:8000", "app:app"]