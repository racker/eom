from eom import proxy
from oslo.config import cfg

conf = cfg.CONF
conf(project='eom', args=[])
app = proxy.ReverseProxy()
