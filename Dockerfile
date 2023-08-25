FROM abiosoft/caddy:no-stats as caddy

FROM denoland/deno:alpine
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy

RUN apk add git

VOLUME /root/.caddy /srv
WORKDIR /srv

RUN /usr/bin/caddy -version
ENTRYPOINT [ "/usr/bin/caddy" ]
CMD ["--conf", "/etc/Caddyfile", "--log", "stdout", "--agree=true"]

