FROM rust:latest

RUN apt-get update -y \
    apt-get install -y python3-dev python3-venv python3-pip

RUN pip install -y termcolor