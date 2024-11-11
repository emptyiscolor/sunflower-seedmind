package service

import (
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	ArtifactDir = "/out"
)

type RunSeedsService struct{}

func NewRunSeedsService() *RunSeedsService {
	return &RunSeedsService{}
}

func (s *RunSeedsService) RunSeeds(ctx context.Context, req *runtime.RunSeedsRequest) (*runtime.RunSeedsResponse, error) {
	log.Printf("Running seeds for harness binary: %s with %d seeds",
		req.HarnessBinary, len(req.SeedsPath))

	if err := validatePaths(req.HarnessBinary, req.SeedsPath); err != nil {
		return nil, status.Error(codes.NotFound, err.Error())
	}

	if err := dryRunSeeds(req.HarnessBinary, req.SeedsPath); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	if err := checkGetCovBinary(); err != nil {
		return nil, status.Error(codes.Unavailable, err.Error())
	}

	coverage, err := runGetCov(req.HarnessBinary, req.SeedsPath)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &runtime.RunSeedsResponse{
		Coverage: coverage,
	}, nil
}

func validatePaths(harnessBinary string, seedsPaths []string) error {
	// Check if harness binary exists
	if _, err := os.Stat(harnessBinary); os.IsNotExist(err) {
		log.Printf("Error: harness binary not found at path: %s", harnessBinary)
		return fmt.Errorf("harness binary not found at path: %s", harnessBinary)
	}

	// Check if all seed files exist
	for _, seedPath := range seedsPaths {
		if _, err := os.Stat(seedPath); os.IsNotExist(err) {
			log.Printf("Error: seed file not found at path: %s", seedPath)
			return fmt.Errorf("seed file not found at path: %s", seedPath)
		}
	}

	return nil
}

func checkGetCovBinary() error {
	// Check if getcov binary exists in PATH
	if _, err := os.Stat("/getcov"); os.IsNotExist(err) {
		log.Printf("Error: getcov binary not found")
		return fmt.Errorf("getcov binary not found")
	}
	return nil
}

func runGetCov(harnessBinary string, seedsPaths []string) (string, error) {
	// Create a temporary directory to hold seeds
	tmpDir, err := os.MkdirTemp("", "seeds-*")
	if err != nil {
		log.Printf("Error: failed to create temporary directory: %v", err)
		return "", fmt.Errorf("failed to create temporary directory: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Copy all seeds to temporary directory
	for _, seedPath := range seedsPaths {
		seedName := filepath.Base(seedPath)
		destPath := filepath.Join(tmpDir, seedName)

		if err := copyFile(seedPath, destPath); err != nil {
			log.Printf("Error: failed to copy seed %s: %v", seedPath, err)
			return "", fmt.Errorf("failed to copy seed %s: %v", seedPath, err)
		}
	}

	// Run getcov like this: getcov -i <seed_dir> -- <harness_binary> @@
	getcovCmd := exec.Command("/getcov", "-i", tmpDir, "--", harnessBinary, "@@")
	getcovCmd.Dir = ArtifactDir

	// run the command
	output, err := getcovCmd.CombinedOutput()
	if err != nil {
		log.Printf("Error: failed to run getcov: %v\nOutput: %s", err, string(output))
		return "", fmt.Errorf("failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	return string(output), nil
}

func dryRunSeeds(harnessBinary string, seedsPaths []string) error {
	// set EXPORT_CALLS=1 and run the seeds with harness binary one by one, and collect the call graph
	for _, seedPath := range seedsPaths {
		os.Setenv("EXPORT_CALLS", "1")
		cmd := exec.Command(harnessBinary, seedPath)
		cmd.Run()
		UpdateCallGraph()
	}
	return nil
}

func copyFile(src, dst string) error {
	input, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, input, 0644)
}
