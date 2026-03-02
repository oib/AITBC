with open("/home/oib/windsurf/aitbc/test_multi_chain.py", "r") as f:
    content = f.read()

content = content.replace("127.0.0.1:8181/rpc/health", "127.0.0.1:8181/health")

with open("/home/oib/windsurf/aitbc/test_multi_chain.py", "w") as f:
    f.write(content)
