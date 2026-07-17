# Validation sandboxing

Static analysis is the default and safest ProofStack capability. Running a repository's test,
build, or installation commands is a separate trust decision. A command being useful does
not make its input safe.

## NativeSafeRunner

The native runner is designed for the checked-in Demo and trusted local repositories. It:

- accepts structured argument arrays only;
- allows a small executable and subcommand set;
- fixes the working directory under the prepared source;
- filters inherited environment variables;
- enforces a timeout and output limit;
- terminates the child process group; and
- redacts stdout and stderr before persistence.

It is not an operating-system sandbox. A permitted interpreter or test tool can execute
project code with the current user's authority. Do not point it at an untrusted repository.

## DockerSandboxRunner

The optional Docker runner mounts source read-only, uses a separate writable output area,
selects a non-root user, disables the network by default, sets CPU, memory and PID limits,
drops capabilities, enables no-new-privileges, and applies a hard timeout and cleanup path.
It never requests privileged mode and never mounts the Docker Socket into the analysis
container.

The host process still needs permission to talk to a container runtime. Granting a service
the Docker Socket is effectively granting host administration. ProofStack's Compose file
therefore does not enable the Docker runner or mount the socket. Operators who create a
separate execution service must document, isolate, monitor, and accept that risk explicitly.

## Recommended decision

Use static analysis for arbitrary uploads. Use native validation only for code you already
trust to run as your local user. Use the container adapter for bounded defense in depth, and
use a disposable VM or dedicated sandbox service when repository authors are adversarial.
Unavailable Docker validation must remain `unavailable`; do not reinterpret it as passed.
