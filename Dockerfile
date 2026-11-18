FROM python:3.12-slim
WORKDIR /app
COPY server.py bitchord_addon_auth.py ./
RUN pip install --no-cache-dir cryptography
ENV PORT=8080
EXPOSE 8080
CMD ["python", "server.py"]
