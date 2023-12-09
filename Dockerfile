# set base image (host OS)
FROM zaandahl/mewc-detect:latest

# set the working directory in the container
WORKDIR /code

# copy code
COPY src/ .

# run mewc_snip on start
CMD [ "python", "./mewc_snip.py" ]