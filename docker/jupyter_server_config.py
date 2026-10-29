# JupyterLab as the image serves it. Docker publishes its port on the
# attendee's own computer alone (127.0.0.1), and the launcher passes the token
# in JUPYTER_TOKEN, which Jupyter reads itself.
c = get_config()  # noqa: F821
c.ServerApp.ip = "0.0.0.0"
c.ServerApp.port = 8888
c.ServerApp.open_browser = False
c.ServerApp.root_dir = "/home/mri"
# Requests reach the server from Docker's network, not from its own host.
c.ServerApp.allow_remote_access = True
# A terminal opens a login shell in the attendee's home.
c.ServerApp.terminado_settings = {"shell_command": ["/bin/bash", "-l"]}
