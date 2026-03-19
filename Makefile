CPPFLAGS=-D_POSIX_C_SOURCE=200809L
CFLAGS=-std=c99 -Wall -Wpedantic -ggdb3

.PHONY: all clean test
all: device

clean:
	-rm *.o device
