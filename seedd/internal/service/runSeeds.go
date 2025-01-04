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
	"sync"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Constants grouped by purpose
const (
	// FileSystem paths
	artifactDir  = "/out"
	getCovBinary = "/getcov"
)

// GetCovConfig holds the configuration for running coverage analysis
type GetCovConfig struct {
	HarnessBinary string   // Path to the harness binary
	SeedsPaths    []string // List of paths to seed files
}

// RunSeedsService implements the seed running service
type RunSeedsService struct {
	mergedProfdataPath map[string]string     // key: harness binary, value: merged profdata path
	callGraphs         map[string]*CallGraph // key: harness binary, value: call graph

	callGraphUpdateMutex sync.Mutex // when dry run seeds, ensure the call graph is updated atomically
}

// NewRunSeedsService creates a new instance of RunSeedsService
func NewRunSeedsService() *RunSeedsService {
	return &RunSeedsService{
		mergedProfdataPath: make(map[string]string),
		callGraphs:         make(map[string]*CallGraph),
	}
}

// RunSeeds executes the seed files and collects coverage information
func (s *RunSeedsService) RunSeeds(ctx context.Context, req *runtime.RunSeedsRequest) (*runtime.RunSeedsResponse, error) {
	logger := log.Default() // Consider using a proper logging framework
	logger.Printf("Running seeds for harness binary: %s with %d seeds", req.HarnessBinary, len(req.SeedsPath))

	if err := s.validateAndPrepare(req.HarnessBinary, req.SeedsPath); err != nil {
		return nil, err
	}

	config := GetCovConfig{
		HarnessBinary: req.HarnessBinary,
		SeedsPaths:    req.SeedsPath,
	}

	coverage, report, profdataPath, err := config.runGetCovAndParse()
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	if err := s.mergeProfdata(req.HarnessBinary, profdataPath); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &runtime.RunSeedsResponse{
		Coverage: coverage,
		Report:   report,
	}, nil
}

// validateAndPrepare combines all preparation steps
func (s *RunSeedsService) validateAndPrepare(harnessBinary string, seedsPaths []string) error {
	if err := validatePaths(harnessBinary, seedsPaths); err != nil {
		return status.Error(codes.NotFound, err.Error())
	}

	if err := s.dryRunSeeds(harnessBinary, seedsPaths); err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	if err := checkGetCovBinary(); err != nil {
		return status.Error(codes.Unavailable, err.Error())
	}

	return nil
}

// runGetCovAndParse executes getcov and parses its output
func (c *GetCovConfig) runGetCovAndParse() (coverage, report, profdataPath string, err error) {
	output, err := c.runGetCov()
	if err != nil {
		return "", "", "", err
	}

	return parseGetCovOutput(output)
}

// parseGetCovOutput parses the output from getcov into its components
func parseGetCovOutput(output string) (coverage, report, profdataPath string, err error) {
	parts := strings.Split(output, "\n<<<JSON_OUTPUT_END>>>\n")
	if len(parts) != 2 {
		return "", "", "", fmt.Errorf("invalid output format from getcov")
	}

	coverage = parts[0]
	remainingOutput := parts[1]

	parts = strings.Split(remainingOutput, "\n<<<TEXT_OUTPUT_END>>>\n")
	if len(parts) != 2 {
		return "", "", "", fmt.Errorf("invalid output format from getcov")
	}

	profdataPath = strings.TrimSpace(parts[1])

	return coverage, parts[0], profdataPath, nil
}

func (s *RunSeedsService) GetMergedCoverage(ctx context.Context, req *runtime.GetMergedCoverageRequest) (*runtime.RunSeedsResponse, error) {
	log.Printf("Getting merged coverage for harness binary: %s", req.HarnessBinary)

	if _, ok := s.mergedProfdataPath[req.HarnessBinary]; !ok {
		return nil, status.Error(codes.NotFound, "merged profdata path not found")
	}

	mergedProfdataPath := s.mergedProfdataPath[req.HarnessBinary]

	getcovCmd := exec.Command(getCovBinary, "--hybrid", "--profdata", mergedProfdataPath, "--", req.HarnessBinary, "@@")
	getcovCmd.Dir = artifactDir

	output, err := getcovCmd.CombinedOutput()
	if err != nil {
		log.Printf("Error: failed to run getcov: %v\nOutput: %s", err, string(output))
		return nil, status.Errorf(codes.Internal, "failed to run getcov: %v\nOutput: %s", err, string(output))
	}

	coverage, report, _, err := parseGetCovOutput(string(output))
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to parse getcov output: %v", err)
	}

	return &runtime.RunSeedsResponse{
		Coverage: coverage,
		Report:   report,
	}, nil
}

// Merge provided profdata file to the merged_profdata_path
func (s *RunSeedsService) mergeProfdata(harnessBinary string, profdataPath string) error {
	// check if merged_profdata_path contains the harnessBinary
	if mergedProfdataPath, ok := s.mergedProfdataPath[harnessBinary]; ok {
		// merge the profdata file to the merged_profdata_path
		// run `llvm-profdata merge -o <merged.profdata> <profdata_path> <merged.profdata>`
		cmd := exec.Command("llvm-profdata", "merge", "-o", mergedProfdataPath, profdataPath, mergedProfdataPath)
		return cmd.Run()
	} else {
		// create a new merged_profdata_path for the harnessBinary
		mergedProfdataFilename := fmt.Sprintf("merged_%s.profdata", harnessBinary)
		mergedProfdataPath := filepath.Join(artifactDir, mergedProfdataFilename)
		s.mergedProfdataPath[harnessBinary] = mergedProfdataPath
		// copy the profdata file to the merged_profdata_path
		if err := copyFile(profdataPath, mergedProfdataPath); err != nil {
			return err
		}
	}
	return nil
}

// validatePaths checks if all required files exist and paths are valid
// It verifies both the harness binary and seed files
func validatePaths(harnessBinary string, seedsPaths []string) error {
	// Check if harness binary is an absolute path
	if !filepath.IsAbs(harnessBinary) {
		harnessBinary = filepath.Join(artifactDir, harnessBinary)
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
	if _, err := os.Stat(getCovBinary); os.IsNotExist(err) {
		log.Printf("Error: getcov binary not found")
		return fmt.Errorf("getcov binary not found")
	}
	return nil
}

// runGetCov executes the getcov tool with the provided configuration
// It creates a temporary directory for seeds, runs the analysis, and returns the output
func (c *GetCovConfig) runGetCov() (string, error) {
	tmpDir, err := prepareSeedDirectory(c.SeedsPaths)
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(tmpDir) // Clean up temporary directory after execution

	// Prepare command line arguments for getcov
	args := []string{"-i", tmpDir}
	args = append(args, "--hybrid")
	args = append(args, "--", c.HarnessBinary, "@@")

	// Execute getcov command
	getcovCmd := exec.Command(getCovBinary, args...)
	getcovCmd.Dir = artifactDir

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

// copyFile copies a file from src to dst
// If the destination file exists, it will be overwritten
func copyFile(src, dst string) error {
	input, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, input, 0644)
}
