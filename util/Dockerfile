FROM krlmlr/debian-ssh:latest
RUN sudo apt update
RUN sudo apt install curl wget git -y
RUN curl -sL https://deb.nodesource.com/setup_15.x | sudo -E bash -
RUN sudo apt install nodejs -y
RUN su docker && git config --global user.name 'deltaryz' && git config --global user.email 'wincam97@gmail.com'
CMD ["sh", "/run.sh"]
