# Builds ocl_test without OpenCL dev headers: links straight against the ICD loader.
OCL := $(shell (ldconfig -p 2>/dev/null | grep -oP '/\S+libOpenCL\.so\.1$$'; find /usr/lib /usr/lib64 -name 'libOpenCL.so.1' 2>/dev/null) | head -1)
CFLAGS ?= -O2
all: bin/ocl_test
bin/ocl_test: src/ocl_test.c
	@test -n "$(OCL)" || { echo "libOpenCL.so.1 not found: install ocl-icd-libopencl1 (and an ICD, e.g. mesa-opencl-icd)"; exit 1; }
	$(CC) $(CFLAGS) -o $@ $< $(OCL)
clean: ; rm -f bin/ocl_test
.PHONY: all clean
