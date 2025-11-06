import torch, sys
print("Python:", sys.version.splitlines()[0])
print("torch:", torch.__version__)
print("torch.cuda.is_available():", torch.cuda.is_available())
print("torch.version.cuda:", torch.version.cuda)
try:
    print("cuda devices:", torch.cuda.device_count(), [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
except Exception as e:
    print("cuda device error:", e)
