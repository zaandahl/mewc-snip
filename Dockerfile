# Required: use the fixed parent built from the matching source lock.
ARG MEWC_DETECT_BASE
FROM ${MEWC_DETECT_BASE}
WORKDIR /code
COPY src/ .
CMD ["python", "./mewc_snip.py"]
