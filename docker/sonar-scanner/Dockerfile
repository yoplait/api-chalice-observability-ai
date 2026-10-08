# ARM64 SonarScanner CLI.
# Context (verified on this host 2026-10-08): the official
# sonarsource/sonar-scanner-cli image only publishes linux/amd64 and its native
# launcher CRASHES under emulation on Apple Silicon ("Failed to find vdso DT_HASH").
# The distribution itself is portable: bin/sonar-scanner is a POSIX sh script and
# lib/*.jar is plain Java bytecode. We therefore extract /opt/sonar-scanner from
# the upstream image (layers are read, never executed during COPY) and run it on
# a native ARM64 JRE.
FROM --platform=linux/amd64 sonarsource/sonar-scanner-cli:latest AS dist

FROM eclipse-temurin:21-jre
COPY --from=dist /opt/sonar-scanner /opt/sonar-scanner
ENV PATH="/opt/sonar-scanner/bin:${PATH}"
WORKDIR /project
ENTRYPOINT ["sonar-scanner"]
