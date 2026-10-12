"""A sandbox launcher for untrusted programs: Landlock filesystem and network rules plus seccomp filters.

Symblic runs code it does not trust: JavaScript a model wrote (symblic.js.check runs node under this launcher)
and, in the autogen tools, agent CLIs and model-written test scripts. This launcher restricts such a process
before it starts, using only features an unprivileged user has on Linux:

  * Landlock (Linux 5.13+, ABI 1+) allowlists the filesystem: system directories read-only, the program's
    own install read/exec, the directories the caller names read-write, and nothing else. The rest of $HOME
    (source checkouts, keys, configuration) is not there for the program.
  * Landlock scoping (ABI 6+) stops it signalling processes outside the sandbox.
  * no_new_privs and a new session (the caller kills the whole process group on timeout). The caller passes
    a minimal environment, so none of its own secrets reach the program.

Why not bubblewrap: distributions such as Ubuntu set kernel.apparmor_restrict_unprivileged_userns=1, so
unprivileged user namespaces fail without root. Why a separate launcher process (`python3 landlock.py ...`)
instead of a preexec_fn: preexec_fn is unsafe in a threaded parent.

    python3 landlock.py [--ro P]... [--rx P]... [--rw P]... [--cwd D]
                        [--require] [--no-unix] [--net-connect PORTS]
                        [--net-bind-ephemeral] -- CMD ARG...

--require refuses to run (exit 125) when Landlock is unavailable; use it whenever the program is untrusted.
Without it, a missing Landlock degrades to "minimal environment + scratch directory" with a warning.

--no-unix adds a seccomp filter: socket(AF_UNIX) and io_uring fail with EACCES, so the program cannot reach
local Unix sockets (the systemd user bus, a terminal multiplexer, ...). socketpair() stays allowed.

--net-connect PORTS (comma list, e.g. 443,80; ABI 4+) adds Landlock network rules: TCP connect is allowed
only to those ports and TCP bind is denied, so local web services that trust loopback callers become
unreachable. The JavaScript adapter passes port 1, which nothing listens on: no network at all. Landlock only
mediates plain TCP connect(), so the flag also stacks a seccomp filter (net_socket_filter) that closes the
ways around it: MPTCP and other inet protocols, TCP Fast Open sends, exotic socket families, TCP_ULP and
io_uring. UDP (DNS) and Unix sockets are not network rules (--no-unix covers the latter). On an older kernel
it refuses with --require; without --require it warns and keeps the filesystem rules.

--net-bind-ephemeral (only with --net-connect) lets the program bind a TCP socket to port 0, i.e. to a
kernel-chosen port, and nothing else: some agent CLIs open such a helper listener on 127.0.0.1:0 and exit
without it. Binding a fixed port stays denied, and the connect rules are unchanged.

Stdlib only and self-contained: symblic.js.check copies this file into a fresh scratch directory and runs the
copy. Its bytes are part of the kernel identity (symblic.kernel.language.kernel_id, through the JavaScript
adapter's asset hash). Linux on x86_64 or aarch64 only.
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys

# x86_64 / aarch64 generic syscall numbers (identical on both since 5.13).
SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

FS_EXECUTE = 1 << 0
FS_WRITE_FILE = 1 << 1
FS_READ_FILE = 1 << 2
FS_READ_DIR = 1 << 3
FS_REMOVE_DIR = 1 << 4
FS_REMOVE_FILE = 1 << 5
FS_MAKE_CHAR = 1 << 6
FS_MAKE_DIR = 1 << 7
FS_MAKE_REG = 1 << 8
FS_MAKE_SOCK = 1 << 9
FS_MAKE_FIFO = 1 << 10
FS_MAKE_BLOCK = 1 << 11
FS_MAKE_SYM = 1 << 12
FS_REFER = 1 << 13        # ABI 2
FS_TRUNCATE = 1 << 14     # ABI 3
FS_IOCTL_DEV = 1 << 15    # ABI 5

SCOPE_ABSTRACT_UNIX_SOCKET = 1 << 0   # ABI 6
SCOPE_SIGNAL = 1 << 1                 # ABI 6

NET_BIND_TCP = 1 << 0                 # ABI 4
NET_CONNECT_TCP = 1 << 1              # ABI 4
LANDLOCK_RULE_NET_PORT = 2
NET_ABI = 4
NET_ABI_ERROR = 'network rules need Landlock ABI 4'

# Rights that can be granted on a regular file (the rest only make sense on
# a directory, and the kernel rejects them on a file rule).
_FILE_RIGHTS = FS_EXECUTE | FS_WRITE_FILE | FS_READ_FILE | FS_TRUNCATE | FS_IOCTL_DEV

# System locations every CLI needs: binaries and libraries (read + exec), and
# config, certs, DNS and a little of /proc and /sys (read only). /proc/self
# resolves to the launcher's own pid, which the exec'd program keeps; other
# processes' /proc entries (for example another process's environ) stay out of reach.
SYSTEM_RX = ('/usr', '/lib', '/lib64', '/lib32', '/bin', '/sbin', '/opt')
SYSTEM_RO = ('/etc', '/run/systemd/resolve', '/sys/fs/cgroup', '/sys/devices/system/cpu',
             '/proc/self', '/proc/cpuinfo', '/proc/meminfo', '/proc/stat', '/proc/filesystems')
SYSTEM_RW = ('/dev/null', '/dev/zero', '/dev/random', '/dev/urandom', '/dev/tty',
             '/dev/pts', '/dev/ptmx', '/dev/shm')


def abi_version() -> int:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        v = libc.syscall(SYS_LANDLOCK_CREATE_RULESET, None, ctypes.c_size_t(0),
                         ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION))
        return int(v) if v > 0 else 0
    except (OSError, AttributeError):
        return 0


def handled_fs(abi: int) -> int:
    rights = (FS_EXECUTE | FS_WRITE_FILE | FS_READ_FILE | FS_READ_DIR | FS_REMOVE_DIR
              | FS_REMOVE_FILE | FS_MAKE_CHAR | FS_MAKE_DIR | FS_MAKE_REG | FS_MAKE_SOCK
              | FS_MAKE_FIFO | FS_MAKE_BLOCK | FS_MAKE_SYM)
    if abi >= 2:
        rights |= FS_REFER
    if abi >= 3:
        rights |= FS_TRUNCATE
    if abi >= 5:
        rights |= FS_IOCTL_DEV
    return rights


def rights_for(mode: str, abi: int) -> int:
    ro = FS_READ_FILE | FS_READ_DIR
    if mode == 'ro':
        return ro
    if mode == 'rx':
        return ro | FS_EXECUTE
    # rw: everything we handle, including exec (CLIs unpack helpers into
    # their own dirs and run them).
    return handled_fs(abi)


def ruleset_attr(abi: int, net: bool = False) -> bytes:
    """struct landlock_ruleset_attr for this ABI: handled_access_fs, then
    handled_access_net (ABI 4) and scoped (ABI 6). Without net rules the
    layout is exactly what it always was."""
    handled = handled_fs(abi)
    handled_net = (NET_BIND_TCP | NET_CONNECT_TCP) if net else 0
    if abi >= 6:
        return struct.pack('=QQQ', handled, handled_net, SCOPE_SIGNAL)
    if net:
        return struct.pack('=QQ', handled, handled_net)
    return struct.pack('=Q', handled)


def parse_ports(text: str) -> list[int]:
    """'443,80' -> [443, 80]. An empty string means no TCP connect at all."""
    ports = []
    for part in (text or '').split(','):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 0 < int(part) < 65536:
            raise ValueError(f'bad port {part!r}')
        if int(part) not in ports:
            ports.append(int(part))
    return ports


def restrict(ro=(), rx=(), rw=(), abi: int | None = None, net_ports=None, bind_ephemeral: bool = False) -> int:
    """Apply Landlock to the current process. Returns the ABI used; raises
    OSError if the kernel refuses. Paths that don't exist are skipped.
    net_ports (a list, possibly empty) also denies TCP bind and every TCP
    connect except to those ports; None leaves the network alone.
    bind_ephemeral (with net_ports) allows bind() to port 0 only: Landlock maps
    a port-0 bind rule to the ephemeral range and to nothing else."""
    abi = abi_version() if abi is None else abi
    if abi < 1:
        raise OSError('Landlock is not available on this kernel')
    net = net_ports is not None
    if bind_ephemeral and not net:
        raise ValueError('bind_ephemeral needs net_ports')
    if net and abi < NET_ABI:
        raise OSError(f'{NET_ABI_ERROR} (this kernel has ABI {abi})')
    libc = ctypes.CDLL(None, use_errno=True)
    handled = handled_fs(abi)
    attr = ruleset_attr(abi, net)
    buf = ctypes.create_string_buffer(attr, len(attr))
    ruleset = libc.syscall(SYS_LANDLOCK_CREATE_RULESET, buf, ctypes.c_size_t(len(attr)),
                           ctypes.c_uint32(0))
    if ruleset < 0:
        raise OSError(ctypes.get_errno(), 'landlock_create_ruleset failed')
    try:
        for mode, paths in (('ro', ro), ('rx', rx), ('rw', rw)):
            for path in paths:
                try:
                    fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
                except OSError:
                    continue
                try:
                    access = rights_for(mode, abi) & handled
                    if not os.path.isdir(path):
                        access &= _FILE_RIGHTS
                    rule = ctypes.create_string_buffer(struct.pack('=Qi', access, fd), 12)
                    if libc.syscall(SYS_LANDLOCK_ADD_RULE, ctypes.c_int(ruleset),
                                    ctypes.c_uint32(LANDLOCK_RULE_PATH_BENEATH), rule,
                                    ctypes.c_uint32(0)) < 0:
                        raise OSError(ctypes.get_errno(), f'landlock_add_rule failed for {path}')
                finally:
                    os.close(fd)
        for access, port in ([(NET_BIND_TCP, 0)] if bind_ephemeral else []) + \
                [(NET_CONNECT_TCP, p) for p in (net_ports or ())]:
            rule = ctypes.create_string_buffer(struct.pack('=QQ', access, int(port)), 16)
            if libc.syscall(SYS_LANDLOCK_ADD_RULE, ctypes.c_int(ruleset),
                            ctypes.c_uint32(LANDLOCK_RULE_NET_PORT), rule, ctypes.c_uint32(0)) < 0:
                raise OSError(ctypes.get_errno(), f'landlock_add_rule failed for port {port}')
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'prctl(NO_NEW_PRIVS) failed')
        if libc.syscall(SYS_LANDLOCK_RESTRICT_SELF, ctypes.c_int(ruleset), ctypes.c_uint32(0)) < 0:
            raise OSError(ctypes.get_errno(), 'landlock_restrict_self failed')
    finally:
        os.close(ruleset)
    return abi


# --- seccomp -----------------------------------------------------------------
# Landlock mediates files, not connect() on a Unix socket path. An agent with
# tools could otherwise reach the systemd user bus (/run/user/<uid>/bus ->
# StartTransientUnit runs a process outside this sandbox) or the web
# terminal's tmux socket. With --no-unix, socket(AF_UNIX, ...) and io_uring
# (which can create sockets without the socket syscall) fail with EACCES.
# socketpair() stays allowed: runtimes use it for child stdio.

PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
AF_UNIX = 1
EACCES = 13
_ARCHES = {  # machine -> (AUDIT_ARCH, socket nr, io_uring_setup nr, x32 bit)
    'x86_64': (0xC000003E, 41, 425, 0x40000000),
    'aarch64': (0xC00000B7, 198, 425, 0),
}


class _SockFilter(ctypes.Structure):
    _fields_ = [('code', ctypes.c_uint16), ('jt', ctypes.c_uint8),
                ('jf', ctypes.c_uint8), ('k', ctypes.c_uint32)]


class _SockFprog(ctypes.Structure):
    _fields_ = [('len', ctypes.c_uint16), ('filter', ctypes.POINTER(_SockFilter))]


def unix_socket_filter(machine: str | None = None) -> list[tuple[int, int, int, int]]:
    """Classic BPF: deny socket(AF_UNIX) and io_uring_setup, allow the rest.
    Unknown architectures (and the x32 syscall range on x86_64) are denied
    wholesale rather than let through unchecked."""
    machine = machine or os.uname().machine
    if machine not in _ARCHES:
        raise OSError(f'no seccomp filter for {machine}')
    arch, nr_socket, nr_uring, x32 = _ARCHES[machine]
    LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06
    deny = SECCOMP_RET_ERRNO | EACCES
    prog = [
        (LD, 0, 0, 4),                       # 0 A = arch
        (JEQ, 1, 0, arch),                   # 1 arch ok? -> 3
        (RET, 0, 0, deny),                   # 2 foreign arch: deny
        (LD, 0, 0, 0),                       # 3 A = nr
    ]
    if x32:
        prog.append((JGE, 0, 1, x32))        # 4 x32 syscall? -> deny
        prog.append((RET, 0, 0, deny))       # 5
    prog += [
        (JEQ, 0, 1, nr_uring),               # io_uring_setup?
        (RET, 0, 0, deny),
        (JEQ, 0, 3, nr_socket),              # socket? else -> allow
        (LD, 0, 0, 16),                      # A = args[0] (low 32 bits)
        (JEQ, 0, 1, AF_UNIX),                # AF_UNIX? else -> allow
        (RET, 0, 0, deny),
        (RET, 0, 0, SECCOMP_RET_ALLOW),
    ]
    return prog


# --- the --net-connect filter --------------------------------------------------
# Landlock's TCP rules only see connect()/bind() on plain TCP sockets. Observed on a
# Linux 7.0 machine (net.mptcp.enabled=1, tcp_fastopen=1) with the rules alone: an
# MPTCP socket (IPPROTO_MPTCP, which falls back to TCP) and a TCP Fast Open send
# (sendto(MSG_FASTOPEN) connects inside tcp_sendmsg, never through the connect hook)
# both reached a denied 127.0.0.1 port, i.e. a local service that trusts loopback.
# So with --net-connect a second filter is stacked on the first (seccomp takes the
# strictest answer) and denies with EACCES:
#   * socket() outside AF_UNIX/AF_INET/AF_INET6/AF_NETLINK (AF_SMC wraps TCP too);
#   * inet sockets other than SOCK_STREAM/SOCK_DGRAM with protocol 0, TCP or UDP
#     (MPTCP 262, SCTP, IPPROTO_SMC, raw, ping);
#   * MSG_FASTOPEN on sendto/sendmsg/sendmmsg (the kernel takes the flags argument);
#   * setsockopt(SOL_TCP, TCP_ULP) (the "smc" ULP turns a TCP socket into SMC);
#   * io_uring_setup (its SOCKET/SEND ops skip these syscalls).
# TCP_FASTOPEN_CONNECT is not a gap: connect() still runs the Landlock hook.
AF_INET, AF_INET6, AF_NETLINK = 2, 10, 16
SOCK_STREAM, SOCK_DGRAM, SOCK_TYPE_MASK = 1, 2, 0xF
IPPROTO_TCP, IPPROTO_UDP = 6, 17
SOL_TCP, TCP_ULP = 6, 31
MSG_FASTOPEN = 0x20000000
_NET_NRS = {
    'x86_64': {'socket': 41, 'sendto': 44, 'sendmsg': 46, 'setsockopt': 54, 'sendmmsg': 307,
               'io_uring_setup': 425},
    'aarch64': {'socket': 198, 'sendto': 206, 'sendmsg': 211, 'setsockopt': 208, 'sendmmsg': 269,
                'io_uring_setup': 425},
}


def _assemble(items: list) -> list[tuple[int, int, int, int]]:
    """Resolve string jump targets (labels are bare strings in `items`) into BPF offsets."""
    labels, prog = {}, []
    for it in items:
        if isinstance(it, str):
            labels[it] = len(prog)
        else:
            prog.append(it)
    out = []
    for i, (code, jt, jf, k) in enumerate(prog):
        offs = []
        for t in (jt, jf):
            d = t if isinstance(t, int) else labels[t] - i - 1
            if not 0 <= d < 256:
                raise ValueError(f'jump out of range at {i}')
            offs.append(d)
        out.append((code, offs[0], offs[1], k))
    return out


def net_socket_filter(machine: str | None = None) -> list[tuple[int, int, int, int]]:
    """Classic BPF for --net-connect (see the block comment above)."""
    machine = machine or os.uname().machine
    if machine not in _ARCHES or machine not in _NET_NRS:
        raise OSError(f'no seccomp filter for {machine}')
    arch, _, _, x32 = _ARCHES[machine]
    nr = _NET_NRS[machine]
    LD, JEQ, JGE, JSET, AND, RET = 0x20, 0x15, 0x35, 0x45, 0x54, 0x06
    deny = SECCOMP_RET_ERRNO | EACCES

    def arg(i):
        return 16 + 8 * i                    # low 32 bits of args[i]

    items = [(LD, 0, 0, 4), (JEQ, 0, 'deny', arch), (LD, 0, 0, 0)]
    if x32:
        items.append((JGE, 'deny', 0, x32))
    items += [
        (JEQ, 'deny', 0, nr['io_uring_setup']),
        (JEQ, 'socket', 0, nr['socket']),
        (JEQ, 'flags3', 0, nr['sendto']),
        (JEQ, 'flags3', 0, nr['sendmmsg']),
        (JEQ, 'flags2', 0, nr['sendmsg']),
        (JEQ, 'sockopt', 'allow', nr['setsockopt']),
        'socket', (LD, 0, 0, arg(0)),
        (JEQ, 'inet', 0, AF_INET),
        (JEQ, 'inet', 0, AF_INET6),
        (JEQ, 'allow', 0, AF_UNIX),          # --no-unix's own filter still denies it
        (JEQ, 'allow', 'deny', AF_NETLINK),
        'inet', (LD, 0, 0, arg(1)), (AND, 0, 0, SOCK_TYPE_MASK),
        (JEQ, 'proto', 0, SOCK_STREAM),
        (JEQ, 'proto', 'deny', SOCK_DGRAM),
        'proto', (LD, 0, 0, arg(2)),
        (JEQ, 'allow', 0, 0),
        (JEQ, 'allow', 0, IPPROTO_TCP),
        (JEQ, 'allow', 'deny', IPPROTO_UDP),
        'flags3', (LD, 0, 0, arg(3)), (JSET, 'deny', 'allow', MSG_FASTOPEN),
        'flags2', (LD, 0, 0, arg(2)), (JSET, 'deny', 'allow', MSG_FASTOPEN),
        'sockopt', (LD, 0, 0, arg(1)), (JEQ, 0, 'allow', SOL_TCP),
        (LD, 0, 0, arg(2)), (JEQ, 'deny', 'allow', TCP_ULP),
        'allow', (RET, 0, 0, SECCOMP_RET_ALLOW),
        'deny', (RET, 0, 0, deny),
    ]
    return _assemble(items)


def install_unix_socket_filter() -> None:
    _install_filter(unix_socket_filter())


def install_net_filter() -> None:
    _install_filter(net_socket_filter())


def _install_filter(prog: list) -> None:
    arr = (_SockFilter * len(prog))(*[_SockFilter(*ins) for ins in prog])
    fprog = _SockFprog(len(prog), ctypes.cast(arr, ctypes.POINTER(_SockFilter)))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'prctl(NO_NEW_PRIVS) failed')
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'prctl(SECCOMP) failed')


def _parse(argv: list[str]) -> dict:
    opts = {'ro': [], 'rx': [], 'rw': [], 'cwd': None, 'require': False, 'no_unix': False, 'cmd': [],
            'net_connect': None, 'net_bind_ephemeral': False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--':
            opts['cmd'] = argv[i + 1:]
            break
        if a == '--net-connect' and i + 1 < len(argv):
            try:
                opts['net_connect'] = parse_ports(argv[i + 1])
            except ValueError as e:
                raise SystemExit(f'symblic-sandbox: --net-connect: {e}')
            i += 2
            continue
        if a in ('--ro', '--rx', '--rw', '--cwd') and i + 1 < len(argv):
            key = a[2:]
            if key == 'cwd':
                opts['cwd'] = argv[i + 1]
            else:
                opts[key].append(argv[i + 1])
            i += 2
            continue
        if a in ('--require', '--no-unix', '--net-bind-ephemeral'):
            opts[a[2:].replace('-', '_')] = True
            i += 1
            continue
        raise SystemExit(f'symblic-sandbox: unknown argument {a!r}')
    if not opts['cmd']:
        raise SystemExit('symblic-sandbox: no command after --')
    if opts['net_bind_ephemeral'] and opts['net_connect'] is None:
        raise SystemExit('symblic-sandbox: --net-bind-ephemeral needs --net-connect')
    return opts


def main(argv: list[str]) -> None:
    opts = _parse(argv)
    if opts['cwd']:
        os.chdir(opts['cwd'])
    net = opts['net_connect']
    if net is not None and abi_version() < NET_ABI:
        if opts['require']:
            sys.stderr.write(f'symblic-sandbox: refusing to run unsandboxed: {NET_ABI_ERROR}\n')
            os._exit(125)
        sys.stderr.write(f'symblic-sandbox: {NET_ABI_ERROR}; running without network rules\n')
        net = None
    try:
        kw = {} if net is None else {'net_ports': net, 'bind_ephemeral': opts['net_bind_ephemeral']}
        restrict(ro=list(SYSTEM_RO) + opts['ro'], rx=list(SYSTEM_RX) + opts['rx'],
                 rw=list(SYSTEM_RW) + opts['rw'] + ([opts['cwd']] if opts['cwd'] else []), **kw)
    except OSError as e:
        if opts['require']:
            sys.stderr.write(f'symblic-sandbox: refusing to run unsandboxed: {e}\n')
            os._exit(125)
        sys.stderr.write(f'symblic-sandbox: Landlock unavailable, running with scrubbed env only: {e}\n')
    if opts['no_unix']:
        try:
            install_unix_socket_filter()
        except OSError as e:
            sys.stderr.write(f'symblic-sandbox: refusing to run without the socket filter: {e}\n')
            os._exit(125)
    if net is not None:
        try:
            install_net_filter()
        except OSError as e:
            sys.stderr.write(f'symblic-sandbox: refusing to run without the network filter: {e}\n')
            os._exit(125)
    try:
        os.execv(opts['cmd'][0], opts['cmd'])
    except OSError as e:
        sys.stderr.write(f'symblic-sandbox: cannot exec {opts["cmd"][0]}: {e}\n')
        os._exit(127)


if __name__ == '__main__':
    main(sys.argv[1:])
