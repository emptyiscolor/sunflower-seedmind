package service

import (
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Package service provides the core business logic for the BugBuster service

// Constants for file system paths
const (
	// ArtifactDir is the directory where artifacts are stored
	ArtifactDir = "/out"
	// GetCovBinary is the path to the getcov binary executable
	GetCovBinary = "/getcov"
)

// GetCovConfig holds the configuration for running coverage analysis
type GetCovConfig struct {
	harnessBinary string   // Path to the harness binary
	seedsPaths    []string // List of paths to seed files
}

// RunSeedsService implements the seed running service
type RunSeedsService struct{}

// NewRunSeedsService creates a new instance of RunSeedsService
func NewRunSeedsService() *RunSeedsService {
	return &RunSeedsService{}
}

// RunSeeds executes the seed files against the harness binary and collects coverage information
// It performs validation, dry run, and coverage analysis using the getcov tool
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

	config := GetCovConfig{
		harnessBinary: req.HarnessBinary,
		seedsPaths:    req.SeedsPath,
	}

	hybrid_output, err := config.runGetCov()
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	// Split the hybrid output into coverage and report
	parts := strings.Split(hybrid_output, "\n<<<JSON_OUTPUT_END>>>\n")
	if len(parts) != 2 {
		return nil, status.Error(codes.Internal, "invalid output format from getcov")
	}

	coverage := parts[0]
	report := parts[1]

	return &runtime.RunSeedsResponse{
		Coverage: coverage,
		Report:   report,
	}, nil
}

// validatePaths checks if all required files exist and paths are valid
// It verifies both the harness binary and seed files
func validatePaths(harnessBinary string, seedsPaths []string) error {
	// Check if harness binary is an absolute path
	if !filepath.IsAbs(harnessBinary) {
		harnessBinary = filepath.Join(ArtifactDir, harnessBinary)
	}

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

// checkGetCovBinary verifies that the getcov binary exists and is accessible
func checkGetCovBinary() error {
	// Check if getcov binary exists in PATH
	if _, err := os.Stat(GetCovBinary); os.IsNotExist(err) {
		log.Printf("Error: getcov binary not found")
		return fmt.Errorf("getcov binary not found")
	}
	return nil
}

// runGetCov executes the getcov tool with the provided configuration
// It creates a temporary directory for seeds, runs the analysis, and returns the output
func (c *GetCovConfig) runGetCov() (string, error) {
	tmpDir, err := prepareSeedDirectory(c.seedsPaths)
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(tmpDir) // Clean up temporary directory after execution

	// Prepare command line arguments for getcov
	args := []string{"-i", tmpDir}
	args = append(args, "--hybrid")
	args = append(args, "--", c.harnessBinary, "@@")

	// Execute getcov command
	getcovCmd := exec.Command(GetCovBinary, args...)
	getcovCmd.Dir = ArtifactDir

	output, err := getcovCmd.CombinedOutput()
	if err != nil {
		log.Printf("Error: failed to run getcov: %v\nOutput: %s", err, string(output))
		return "", fmt.Errorf("failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	return string(output), nil
}

// prepareSeedDirectory creates a temporary directory and copies all seed files into it
// Returns the path to the temporary directory and any error encountered
func prepareSeedDirectory(seedsPaths []string) (string, error) {
	tmpDir, err := os.MkdirTemp("", "seeds-*")
	if err != nil {
		log.Printf("Error: failed to create temporary directory: %v", err)
		return "", fmt.Errorf("failed to create temporary directory: %v", err)
	}

	// Copy each seed file to the temporary directory
	for _, seedPath := range seedsPaths {
		seedName := filepath.Base(seedPath)
		destPath := filepath.Join(tmpDir, seedName)

		if err := copyFile(seedPath, destPath); err != nil {
			os.RemoveAll(tmpDir) // Clean up on error
			log.Printf("Error: failed to copy seed %s: %v", seedPath, err)
			return "", fmt.Errorf("failed to copy seed %s: %v", seedPath, err)
		}
	}

	return tmpDir, nil
}

// dryRunSeeds executes each seed file with the harness binary to collect call graph information
// Sets EXPORT_CALLS=1 environment variable for each run
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

// copyFile copies a file from src to dst
// If the destination file exists, it will be overwritten
func copyFile(src, dst string) error {
	input, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, input, 0644)
}
