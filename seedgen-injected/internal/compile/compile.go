package compile

import (
	"BugBuster/SeedGenInj/internal/runtime"
	"context"
	"log"
	"os"
	"os/exec"
	"strings"
)

var prepared bool = false

func prepare() {
	if prepared {
		return
	}
	prepared = true

	log.Println("[+] Preparing the environment.")
	// Copy /argus to /usr/bin/argus and /usr/bin/argus++
	cmd := exec.Command("cp", "/argus", "/usr/bin/argus")
	err := cmd.Run()
	if err != nil {
		log.Fatalf("Failed to copy argus: %v", err)
	}

	cmd = exec.Command("cp", "/argus", "/usr/bin/argus++")
	err = cmd.Run()
	if err != nil {
		log.Fatalf("Failed to copy argus++: %v", err)
	}
}

func checkArtifact(expected []string) []string {
	var existingBinaries []string
	for _, binary := range expected {
		// we can safely add "/" before binary because AIxCC ensures that out is mapped to the root of the container
		if _, err := os.Stat("/" + binary); err == nil {
			existingBinaries = append(existingBinaries, binary)
		} else {
			log.Printf("Binary %s does not exist: %v", binary, err)
		}
	}
	return existingBinaries
}

func Compile(ctx context.Context, req *runtime.CompileRequest, compileCmd string) (*runtime.CompileResponse, error) {
	prepare()

	log.Println("[+] Start compiling.")
	env := append(os.Environ(),
		"CC=argus",
		"CXX=argus++",
		"BANDFUZZ_NORUNTIME=1",    // disable linking runtime to the target
		"BANDFUZZ_NATIVESANCOV=1", // disable loading our customized sancov.pass
		"DRIVER_PASSTHROUGH=1",    // disable driver replacement
		"AFL_USE_ASAN=1",          // enable ASAN

		"CP_HARNESS_EXTRA_CFLAGS=-fsanitize=fuzzer-no-link",   // enable libfuzzer
		"CP_HARNESS_EXTRA_CXXFLAGS=-fsanitize=fuzzer-no-link", // enable libfuzzer
		"CP_BASE_EXTRA_CFLAGS=-fsanitize=fuzzer-no-link",      // enable libfuzzer
		"CP_BASE_EXTRA_CXXFLAGS=-fsanitize=fuzzer-no-link",    // enable libfuzzer
		"CP_BASE_EXTRA_LDFLAGS=-fsanitize=fuzzer-no-link",     // enable libfuzzer
	)

	cmdParts := strings.Fields(compileCmd)
	cmd := exec.CommandContext(ctx, cmdParts[0], cmdParts[1:]...)
	cmd.Env = env

	compile_log, err := cmd.CombinedOutput()
	if err != nil {
		log.Printf("Compile command failed: %v", err)

		// compile failed, print the log for debugging
		log.Printf("Compile log: %s", compile_log)

		return &runtime.CompileResponse{
			Success:         false,
			HarnessBinaries: nil,
		}, nil
	}

	log.Printf("Expected binaries: %v", req.ExpectedHarnessBinaries)
	existingBinaries := checkArtifact(req.ExpectedHarnessBinaries)
	log.Printf("Existing binaries: %v", existingBinaries)

	response := &runtime.CompileResponse{
		Success:         true,
		HarnessBinaries: existingBinaries,
	}
	return response, nil
}
