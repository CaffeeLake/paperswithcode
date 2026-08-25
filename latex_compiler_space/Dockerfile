# Immutable OCI index for ghcr.io/xu-cheng/texlive-debian:latest, resolved on
# 2026-08-25. Replace only through a reviewed staging image qualification.
FROM ghcr.io/xu-cheng/texlive-debian@sha256:3bdf292b53c04ffa3ca694a5114397859bcd39b6b417c212414e1505e7fe8ec5

USER root
RUN apt-get update \
    && apt-get install --no-install-recommends -y python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 compiler

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt
COPY latex_compiler_contract /app/latex_compiler_contract
COPY latex_compiler_space /app/latex_compiler_space
RUN chown -R compiler:compiler /app

USER compiler
ENV PYTHONUNBUFFERED=1 \
    PWC_LATEX_COMPILER_IMAGE=ghcr.io/xu-cheng/texlive-debian@sha256:3bdf292b53c04ffa3ca694a5114397859bcd39b6b417c212414e1505e7fe8ec5 \
    PWC_LATEX_COMPILER_ENGINE=pdfLaTeX
EXPOSE 7860
CMD ["python3", "-m", "uvicorn", "latex_compiler_space.app:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]
