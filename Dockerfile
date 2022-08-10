# set base image (host OS)
FROM zaandahl/megadetector_v4:latest

# set the working directory in the container
WORKDIR /code

# copy code
COPY src/ .

# run json_snipper on start
CMD [ "python", "./mewc_snip.py" ]