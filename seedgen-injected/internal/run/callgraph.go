package run

import (
	"BugBuster/SeedGenInj/internal/runtime"
	"context"
	"log"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/google/uuid"
)

func ExportCalls(ctx context.Context, req *runtime.ExportCallsRequest) (*runtime.ExportCallsResponse, error) {
	binary := req.GetHarnessBinary()
	seeds := req.GetSeedsPath()

	err_response := &runtime.ExportCallsResponse{
		Success: false,
	}

	tempDir, err := os.MkdirTemp("", "calls")
	if err != nil {
		log.Printf("Failed to create temp dir: %v\n", err)
		return err_response, err
	}
	defer os.RemoveAll(tempDir)

	// Copy seeds into tempDir
	for _, seed := range seeds {
		seed_name := filepath.Base(seed)
		seed_dest := filepath.Join(tempDir, seed_name)

		err := copyFile(seed, seed_dest)
		if err != nil {
			log.Printf("Failed to copy seed file: %v\n", err)
			return err_response, err
		}
	}

	// run command: `<binary> -seed=0 -runs=0 -print_coverage=1 <tempDir>/`
	cmd := exec.Command(binary, "-seed=0", "-runs=0", "-timeout=1", tempDir)
	cmd.Dir = filepath.Dir(binary)
	cmd.Env = append(cmd.Env, "EXPORT_CALLS=1")
	cmd.Run() // ignore error, since seeds may cause the harness to crash

	// copy /tmp/callgraph.log to the shared directory
	sharedDir := "/shared"
	callgraphName := uuid.New().String() + ".log"
	sharedPath := filepath.Join(sharedDir, callgraphName)

	// Move callgraph.log to shared directory
	err = copyFile("/tmp/callgraph.log", sharedPath)
	if err != nil {
		log.Printf("Failed to copy callgraph.log to shared directory: %v\n", err)
		return err_response, err
	}

	// Create the response
	response := &runtime.ExportCallsResponse{
		Success:  true,
		Filename: callgraphName,
	}

	return response, nil
}
