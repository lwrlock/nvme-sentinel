/*
 * nvme_probe.c - Native C Linux NVMe Thermal, APST, PCIe Link & IOPS Probe
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <dirent.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static bool read_line(const char *path, char *out, size_t sz) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return false;
    ssize_t n = read(fd, out, sz - 1);
    close(fd);
    if (n <= 0) return false;
    out[n] = '\0';
    while (n > 0 && (out[n - 1] == '\n' || out[n - 1] == '\r' || out[n - 1] == ' ')) out[--n] = '\0';
    return true;
}

static int64_t read_i64(const char *path, int64_t def) {
    char b[64];
    if (!read_line(path, b, sizeof(b))) return def;
    char *end = NULL;
    long long v = strtoll(b, &end, 10);
    return (end != b) ? (int64_t)v : def;
}

static bool read_block_stat(const char *blk, uint64_t *r_ios, uint64_t *r_sec, uint64_t *w_ios, uint64_t *w_sec, uint64_t *inflight) {
    char sp[128];
    snprintf(sp, sizeof(sp), "/sys/block/%s/stat", blk);
    FILE *f = fopen(sp, "r");
    if (!f) return false;
    unsigned long long ri = 0, rm = 0, rs = 0, rt = 0, wi = 0, wm = 0, ws = 0, wt = 0, inf = 0;
    int cnt = fscanf(f, "%llu %llu %llu %llu %llu %llu %llu %llu %llu",
                     &ri, &rm, &rs, &rt, &wi, &wm, &ws, &wt, &inf);
    fclose(f);
    if (cnt < 9) return false;
    *r_ios = ri; *r_sec = rs; *w_ios = wi; *w_sec = ws; *inflight = inf;
    return true;
}

static void json_esc(const char *s, char *out, size_t sz) {
    size_t j = 0;
    for (size_t i = 0; s && s[i] && j + 2 < sz; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') {
            if (j + 2 >= sz) break;
            out[j++] = '\\'; out[j++] = (char)c;
        } else if (c >= 0x20) out[j++] = (char)c;
    }
    out[j] = '\0';
}

int main(int argc, char *argv[]) {
    bool as_json = false;
    int sample_ms = 120;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--json") == 0 || strcmp(argv[i], "-j") == 0) as_json = true;
        else if (strcmp(argv[i], "--sample-ms") == 0 && i + 1 < argc) {
            sample_ms = atoi(argv[++i]);
            if (sample_ms < 40) sample_ms = 40;
            if (sample_ms > 1500) sample_ms = 1500;
        }
    }

    char model[96] = "Generic NVMe SSD", fw[32] = "—", link_sp[32] = "—", link_w[16] = "—", sched[64] = "none", pm_st[24] = "—";
    read_line("/sys/class/nvme/nvme0/model", model, sizeof(model));
    read_line("/sys/class/nvme/nvme0/firmware_rev", fw, sizeof(fw));
    read_line("/sys/class/nvme/nvme0/device/current_link_speed", link_sp, sizeof(link_sp));
    read_line("/sys/class/nvme/nvme0/device/current_link_width", link_w, sizeof(link_w));
    read_line("/sys/class/nvme/nvme0/device/power/runtime_status", pm_st, sizeof(pm_st));
    read_line("/sys/block/nvme0n1/queue/scheduler", sched, sizeof(sched));
    int64_t ra_kb = read_i64("/sys/block/nvme0n1/queue/read_ahead_kb", 0);
    int64_t rq_aff = read_i64("/sys/block/nvme0n1/queue/rq_affinity", 0);
    int64_t nr_req = read_i64("/sys/block/nvme0n1/queue/nr_requests", 0);
    int64_t apst_us = read_i64("/sys/module/nvme_core/parameters/default_ps_max_latency_us", -1);

    int temp_c = 0;
    DIR *hd = opendir("/sys/class/hwmon");
    if (hd) {
        struct dirent *de;
        while ((de = readdir(hd)) != NULL) {
            if (strncmp(de->d_name, "hwmon", 5) != 0) continue;
            char np[256], nm[32] = "";
            snprintf(np, sizeof(np), "/sys/class/hwmon/%.32s/name", de->d_name);
            if (read_line(np, nm, sizeof(nm)) && strcmp(nm, "nvme") == 0) {
                char tp[256];
                snprintf(tp, sizeof(tp), "/sys/class/hwmon/%.32s/temp1_input", de->d_name);
                int64_t mc = read_i64(tp, 0);
                if (mc > 0) { temp_c = (int)(mc / 1000); break; }
            }
        }
        closedir(hd);
    }

    uint64_t ri0 = 0, rs0 = 0, wi0 = 0, ws0 = 0, inf = 0;
    uint64_t ri1 = 0, rs1 = 0, wi1 = 0, ws1 = 0;
    read_block_stat("nvme0n1", &ri0, &rs0, &wi0, &ws0, &inf);
    usleep((useconds_t)sample_ms * 1000U);
    read_block_stat("nvme0n1", &ri1, &rs1, &wi1, &ws1, &inf);

    double sec = (double)sample_ms / 1000.0;
    double r_iops = (ri1 >= ri0) ? (double)(ri1 - ri0) / sec : 0.0;
    double w_iops = (wi1 >= wi0) ? (double)(wi1 - wi0) / sec : 0.0;
    double r_mbs = (rs1 >= rs0) ? ((double)(rs1 - rs0) * 512.0 / (1024.0 * 1024.0)) / sec : 0.0;
    double w_mbs = (ws1 >= ws0) ? ((double)(ws1 - ws0) * 512.0 / (1024.0 * 1024.0)) / sec : 0.0;

    if (as_json) {
        char me[192], fe[64], le[64], se[96], pe[48];
        json_esc(model, me, sizeof(me));
        json_esc(fw, fe, sizeof(fe));
        json_esc(link_sp, le, sizeof(le));
        json_esc(sched, se, sizeof(se));
        json_esc(pm_st, pe, sizeof(pe));
        printf("{\n"
               "  \"model\": \"%s\", \"firmware\": \"%s\",\n"
               "  \"pcie_link\": \"%s x%s\", \"pm_status\": \"%s\",\n"
               "  \"temp_c\": %d, \"apst_max_latency_us\": %ld,\n"
               "  \"queue\": {\"scheduler\": \"%s\", \"read_ahead_kb\": %ld, \"rq_affinity\": %ld, \"nr_requests\": %ld},\n"
               "  \"io\": {\"read_iops\": %.0f, \"write_iops\": %.0f, \"read_mbs\": %.2f, \"write_mbs\": %.2f, \"inflight\": %llu}\n"
               "}\n",
               me, fe, le, link_w, pe, temp_c, (long)apst_us,
               se, (long)ra_kb, (long)rq_aff, (long)nr_req,
               r_iops, w_iops, r_mbs, w_mbs, (unsigned long long)inf);
    } else {
        printf("=== NVMe Sentinel Telemetry ===\n");
        printf("  Drive : %s (FW %s) | %d C\n", model, fw, temp_c);
        printf("  PCIe  : %s x%s | PM=%s | APST=%ld us\n", link_sp, link_w, pm_st, (long)apst_us);
        printf("  I/O   : Read %.2f MB/s (%.0f IOPS) | Write %.2f MB/s (%.0f IOPS)\n",
               r_mbs, r_iops, w_mbs, w_iops);
    }
    return 0;
}
