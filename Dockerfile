FROM ubuntu:24.04
RUN apt-get update && apt-get install -y build-essential
COPY . /app
WORKDIR /app
RUN make
ENTRYPOINT ["./device"]
CMD ["--deterministic"]
