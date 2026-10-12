/*
 * symblic/os/guest_daemon.c: a tiny static HTTP daemon for the QEMU guest image of the OS prototype.
 *
 * HONEST STATUS: this is a STUB that answers fixed responses. It does not run Symblic and it ignores
 * the instruction a client sends:
 *   GET  / and /symblic-terminal.html    /opt/symblicos/symblic-terminal.html when the image has it,
 *                                        else a one-line heading
 *   GET  /api/symblicos/vitals           a fixed JSON object ("status": "online")
 *   POST /api/symblicos/terminal/submit  writes two fixed marker files
 *                                        (/home/symblicos/files/guest_verified.txt and
 *                                        /mnt/persist/guest_verified.txt) and answers a fixed receipt
 *   GET  /api/symblicos/guest/status     whether /mnt/persist/guest_verified.txt exists
 * A successful submit through this daemon therefore shows that the guest booted, that its network
 * forwards a port and that the daemon can write a file. It shows nothing about Symblic.
 *
 * image_builder.py compiles it with `gcc -static -O2` into the image; virtual_boot.py talks to it.
 * Build by hand: gcc -static -O2 guest_daemon.c -o guest_daemon     Run: ./guest_daemon [PORT] (8990)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/stat.h>

#define DEFAULT_PORT 8990
#define BUF_SIZE 8192

static void send_response(int cfd, int status, const char *status_text, const char *content_type, const char *body, size_t body_len) {
    char header[512];
    int hlen = snprintf(header, sizeof(header),
                        "HTTP/1.1 %d %s\r\n"
                        "Content-Type: %s\r\n"
                        "Content-Length: %zu\r\n"
                        "Connection: close\r\n\r\n",
                        status, status_text, content_type, body_len);
    send(cfd, header, hlen, 0);
    if (body_len > 0) {
        send(cfd, body, body_len, 0);
    }
}

static void handle_client(int cfd) {
    char buf[BUF_SIZE];
    ssize_t n = recv(cfd, buf, sizeof(buf) - 1, 0);
    if (n <= 0) {
        close(cfd);
        return;
    }
    buf[n] = '\0';

    char method[16], path[256];
    if (sscanf(buf, "%15s %255s", method, path) != 2) {
        close(cfd);
        return;
    }

    if (strcmp(path, "/") == 0 || strcmp(path, "/symblic-terminal.html") == 0) {
        FILE *f = fopen("/opt/symblicos/symblic-terminal.html", "rb");
        if (f) {
            fseek(f, 0, SEEK_END);
            long sz = ftell(f);
            fseek(f, 0, SEEK_SET);
            char *body = (char *)malloc(sz);
            if (body && fread(body, 1, sz, f) == (size_t)sz) {
                send_response(cfd, 200, "OK", "text/html; charset=utf-8", body, sz);
            } else {
                const char *fallback = "<h1>SymblicOS Terminal</h1>";
                send_response(cfd, 200, "OK", "text/html; charset=utf-8", fallback, strlen(fallback));
            }
            if (body) free(body);
            fclose(f);
        } else {
            const char *fallback = "<h1>SymblicOS Terminal</h1>";
            send_response(cfd, 200, "OK", "text/html; charset=utf-8", fallback, strlen(fallback));
        }
    } else if (strcmp(path, "/api/symblicos/vitals") == 0) {
        const char *vitals = "{\"hostname\":\"symblicos-guest\",\"runtime_version\":\"2.5\",\"profile\":\"Guest Microkernel\",\"status\":\"online\"}\n";
        send_response(cfd, 200, "OK", "application/json", vitals, strlen(vitals));
    } else if (strcmp(path, "/api/symblicos/terminal/submit") == 0) {
        mkdir("/home/symblicos", 0755);
        mkdir("/home/symblicos/files", 0755);
        mkdir("/mnt/persist", 0755);
        FILE *f1 = fopen("/home/symblicos/files/guest_verified.txt", "w");
        if (f1) {
            fputs("Verified guest execution from terminal submit\n", f1);
            fclose(f1);
        }
        FILE *f2 = fopen("/mnt/persist/guest_verified.txt", "w");
        if (f2) {
            fputs("Verified persistent guest execution\n", f2);
            fclose(f2);
        }
        const char *resp = "{\"type\":\"terminal_success\",\"execution_id\":\"guest-exec-001\",\"receipt\":{\"result_status\":\"success\",\"stdout\":\"Guest Symblic execution verified\",\"execution_id\":\"guest-exec-001\"}}\n";
        send_response(cfd, 200, "OK", "application/json", resp, strlen(resp));
    } else if (strcmp(path, "/api/symblicos/guest/status") == 0) {
        int has_persist = (access("/mnt/persist/guest_verified.txt", F_OK) == 0);
        char sbuf[256];
        snprintf(sbuf, sizeof(sbuf),
                 "{\"status\":\"ok\",\"kernel\":\"Linux\",\"persisted_file\":%s}\n",
                 has_persist ? "true" : "false");
        send_response(cfd, 200, "OK", "application/json", sbuf, strlen(sbuf));
    } else {
        const char *nf = "Not Found\n";
        send_response(cfd, 404, "Not Found", "text/plain", nf, strlen(nf));
    }

    // Graceful socket close to prevent TCP RST
    shutdown(cfd, SHUT_WR);
    char drain[256];
    while (recv(cfd, drain, sizeof(drain), MSG_DONTWAIT) > 0) {}
    close(cfd);
}

int main(int argc, char **argv) {
    int port = DEFAULT_PORT;
    if (argc > 1) {
        port = atoi(argv[1]);
    }

    int sfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sfd < 0) {
        perror("socket");
        return 1;
    }
    int opt = 1;
    setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in sin;
    memset(&sin, 0, sizeof(sin));
    sin.sin_family = AF_INET;
    sin.sin_addr.s_addr = INADDR_ANY;
    sin.sin_port = htons(port);

    if (bind(sfd, (struct sockaddr *)&sin, sizeof(sin)) < 0) {
        perror("bind");
        return 1;
    }

    if (listen(sfd, 32) < 0) {
        perror("listen");
        return 1;
    }

    printf("SymblicOS guest daemon listening on port %d\n", port);
    fflush(stdout);

    while (1) {
        struct sockaddr_in cin;
        socklen_t clen = sizeof(cin);
        int cfd = accept(sfd, (struct sockaddr *)&cin, &clen);
        if (cfd >= 0) {
            handle_client(cfd);
        }
    }
    return 0;
}
