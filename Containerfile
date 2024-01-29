FROM registry.access.redhat.com/ubi9/python-311:latest

COPY requirements.txt ./
RUN pip install -r requirements.txt
RUN ansible-galaxy collection install dellemc.os9 && \
	ansible-galaxy collection install amazon.aws
COPY . ./

CMD [ "gunicorn", "-b", "0.0.0.0:8000", "slack_notifier.app:app"]
