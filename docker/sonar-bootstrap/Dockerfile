FROM alpine:3.20
RUN addgroup -g 1002 boot && adduser -u 1002 -G boot -D boot \
 && apk add --no-cache bash curl jq openssl
WORKDIR /work
USER boot
