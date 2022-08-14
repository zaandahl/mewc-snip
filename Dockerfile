# set base image (host OS)
FROM zaandahl/megadetector:4.1

# set the working directory in the container
WORKDIR /code

# copy code
COPY src/ .

# run mewc_snip on start
CMD [ "python", "./mewc_snip.py" ]