package service

import (
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func runGetCovAll(harnessBinary string) (string, error) {
	// Create a temporary seed file, use /tmp/getcov-hi
	seedFile := "/tmp/getcov-hi"
	// Check if the seed file exists
	if _, err := os.Stat(seedFile); os.IsNotExist(err) {
		// Create the seed file and write "hi" to it
		err := os.WriteFile(seedFile, []byte("hi"), 0644)
		if err != nil {
			return "", fmt.Errorf("failed to create seed file: %v", err)
		}
	}
	defer os.Remove(seedFile)

	getcovCmd := exec.Command("/getcov", "--all", "--", harnessBinary, seedFile)
	getcovCmd.Dir = artifactDir

	output, err := getcovCmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	return string(output), nil
}

func GetFunctions(ctx context.Context, req *runtime.GetFunctionsRequest) (*runtime.GetFunctionsResponse, error) {
	log.Printf("GetFunctions request received: %+v", req)

	if err := checkGetCovBinary(); err != nil {
		return nil, status.Error(codes.Unavailable, err.Error())
	}

	output, err := runGetCovAll(req.HarnessBinary)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &runtime.GetFunctionsResponse{
		Functions: output,
	}, nil
}
