FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ./server /app/server
RUN useradd --system --uid 10001 mxstatus
USER mxstatus
EXPOSE 5000
# The database is in memory: multiple workers would maintain inconsistent state.
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1", "--no-access-log"]
