/*
 * Regression test for CVE-2026-85091 in the patched zlib (built with
 * -fsanitize=address, run in the Dockerfile's build stage).
 *
 * A gzFile on a read-only descriptor makes the direct-write path fail:
 * gzwrite() of more than the internal buffer compresses straight from the
 * caller's buffer, and the write() of the compressed output fails. Unpatched,
 * that leaves strm.next_in pointing into the caller's buffer. After
 * gzclearerr(), gzprintf() formats into next_in + avail_in -- the end of the
 * caller's allocation -- which AddressSanitizer reports as a
 * heap-buffer-overflow. Patched, the input state is reset, so gzprintf()
 * formats into zlib's own buffer.
 *
 * gzprintf() rather than a second gzwrite(): gzwrite()'s buffered path
 * truncates the stale offset to 32 bits, so its overflow lands at an
 * arbitrary heap address that ASan may not be watching. gzprintf() uses the
 * full pointer and always writes just past the caller's buffer.
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <zlib.h>

int main(void) {
    int fd = open("/dev/null", O_RDONLY);
    if (fd < 0) {
        perror("open");
        return 2;
    }
    gzFile gz = gzdopen(fd, "wb");
    if (gz == NULL) {
        fputs("gzdopen failed\n", stderr);
        return 2;
    }

    /* Incompressible, and far more than deflate can hold back: it keeps up
       to ~64 KB of output pending, so with less input it consumes all of it
       before the write fails and nothing stale is left (avail_in == 0). */
    size_t big = 1 << 22;
    unsigned char *buf = malloc(big);
    srand(85091);
    for (size_t i = 0; i < big; i++)
        buf[i] = (unsigned char)rand();
    int n = gzwrite(gz, buf, (unsigned)big);
    printf("gzwrite to a read-only descriptor: %d (expected 0)\n", n);

    gzclearerr(gz);
    n = gzprintf(gz, "%s", "after the failed write");
    printf("gzprintf after gzclearerr: %d\n", n);

    free(buf);
    (void)gzclose(gz);
    puts("ok: no out-of-bounds write");
    return 0;
}
