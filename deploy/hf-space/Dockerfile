# Hugging Face Space (Docker SDK) for the public SkyTrace demo.
# Installs the released package from PyPI and the sample flights from the
# GitHub tag of the same version. The Space secret GEMINI_API_KEY is passed in
# as an environment variable.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

ARG SKYTRACE_VERSION=1.0.0
RUN pip install --no-cache-dir --user "skytrace[web]==${SKYTRACE_VERSION}"

ARG RAW=https://raw.githubusercontent.com/beyzanurulu/SkyTrace/v${SKYTRACE_VERSION}/samples
ADD --chown=user ${RAW}/samples.yaml ${RAW}/px4_sitl_gps_loss.ulg ${RAW}/px4_sitl_motor_failure.ulg ${RAW}/px4_sitl_low_battery.ulg ${RAW}/px4_vtol_short.ulg samples/
COPY --chown=user config.yaml .

EXPOSE 7860
CMD ["skytrace", "serve", "-c", "config.yaml"]
