package coverage

import (
	"BugBuster/SeedGenInj/internal/locate"
	"BugBuster/SeedGenInj/internal/runtime"
	"bufio"
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
)

const numCores = 48 // the number of cores we can use

func CopyDirectory(sourceDir, destDir string) error {
	err := os.MkdirAll(destDir, 0755)
	if err != nil {
		return err
	}
	if !strings.HasSuffix(sourceDir, "/") {
		sourceDir += "/"
	}
	cmd := exec.Command("rsync", "-av", "--delete", sourceDir, destDir)
	_, err = cmd.CombinedOutput()
	if err != nil {
		return err
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

func moveFile(sourcePath, destPath string) error {
	err := os.Rename(sourcePath, destPath)
	if err == nil {
		return nil
	}

	// If rename failed, try copy and delete
	if err := copyFile(sourcePath, destPath); err != nil {
		return fmt.Errorf("failed to copy file: %v", err)
	}

	if err := os.Remove(sourcePath); err != nil {
		return fmt.Errorf("file copied, but failed to delete original: %v", err)
	}

	return nil
}

func MergeSeeds(binary string, targetFolder string, seeds []string) error {
	log.Printf("[+] Merging %d seeds in %s\n", len(seeds), targetFolder)

	// Create target folder if it doesn't exist
	if err := os.MkdirAll(targetFolder, 0755); err != nil {
		return fmt.Errorf("failed to create target folder: %v", err)
	}

	// Create a temporary directory for merging
	tempDir, err := os.MkdirTemp("", "merge_temp")
	if err != nil {
		return fmt.Errorf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	// Move existing seeds from target folder to temp dir
	existingSeeds, err := os.ReadDir(targetFolder)
	if err != nil {
		return fmt.Errorf("failed to read target folder: %v", err)
	}
	for _, seed := range existingSeeds {
		oldPath := filepath.Join(targetFolder, seed.Name())
		newPath := filepath.Join(tempDir, seed.Name())
		if err := moveFile(oldPath, newPath); err != nil {
			return fmt.Errorf("failed to move existing seed: %v", err)
		}
	}

	// Copy new seeds to temp dir
	for _, seed := range seeds {
		seedName := filepath.Base(seed)
		seedDest := filepath.Join(tempDir, seedName)
		if err := copyFile(seed, seedDest); err != nil {
			return fmt.Errorf("failed to copy seed file: %v", err)
		}
	}

	// Perform merging
	if err := mergeSeeds(binary, tempDir, targetFolder); err != nil {
		return fmt.Errorf("failed to merge seeds: %v", err)
	}

	return nil
}

func mergeSeeds(binary, sourceDir, targetDir string) error {
	crashTargetDir := filepath.Join(filepath.Dir(targetDir), "crash")
	os.MkdirAll(crashTargetDir, 0755)
	seeds, err := os.ReadDir(sourceDir)
	if err != nil {
		return fmt.Errorf("failed to read source directory: %v", err)
	}
	originalSeedCount := len(seeds)
	var previousSeedCount int

	const seedThreshold = 1000
	for {
		seeds, err := os.ReadDir(sourceDir)
		if err != nil {
			return fmt.Errorf("failed to read source directory: %v", err)
		}

		currentSeedCount := len(seeds)

		if currentSeedCount <= 1 || (previousSeedCount > 0 && currentSeedCount == previousSeedCount) || currentSeedCount <= seedThreshold {
			// No more merging needed
			break
		}

		log.Printf("[+] New merge iteration with %d seeds\n", currentSeedCount)

		previousSeedCount = currentSeedCount

		batchSize := (len(seeds) + numCores - 1) / numCores
		var wg sync.WaitGroup
		errors := make(chan error, numCores)

		for i := 0; i < numCores; i++ {
			wg.Add(1)
			go func(batchIndex int) {
				defer wg.Done()
				start := batchIndex * batchSize
				end := (batchIndex + 1) * batchSize
				if end > currentSeedCount {
					end = currentSeedCount
				}

				if start >= end {
					return
				}

				batchDir, err := os.MkdirTemp(sourceDir, "batch")
				if err != nil {
					errors <- fmt.Errorf("failed to create batch directory: %v", err)
					return
				}
				defer os.RemoveAll(batchDir)

				resultDir, err := os.MkdirTemp(sourceDir, "result")
				if err != nil {
					errors <- fmt.Errorf("failed to create result directory: %v", err)
					return
				}
				defer os.RemoveAll(resultDir)

				for _, seed := range seeds[start:end] {
					oldPath := filepath.Join(sourceDir, seed.Name())
					newPath := filepath.Join(batchDir, seed.Name())
					if err := moveFile(oldPath, newPath); err != nil {
						errors <- fmt.Errorf("failed to move seed to batch directory: %v", err)
						return
					}
				}

				log.Printf("[+] Merge batch %d: merging %d seeds\n", batchIndex, end-start)

				// prepare an isolated environment for the merge
				// so, as I understand, we shall copy the folder which contains the binary to a temp folder, so we won't mess up with the original folder

				binaryFolder := filepath.Dir(binary)
				tempDir, err := os.MkdirTemp("", "merge-workdir")
				if err != nil {
					errors <- fmt.Errorf("failed to create temp directory: %v", err)
				}
				CopyDirectory(binaryFolder, tempDir)
				defer os.RemoveAll(tempDir)

				newBinary := filepath.Join(tempDir, filepath.Base(binary))

				cmd := exec.Command(newBinary, "-timeout=1", "-merge=1", resultDir, batchDir)
				cmd.Dir = tempDir

				log.Printf("[*] Running command: %s, in directory: %s\n", cmd.String(), cmd.Dir)

				if output, err := cmd.CombinedOutput(); err != nil {
					log.Printf("failed to merge seeds: %v\nOutput:\n%s", err, string(output))
					// We ignore the error here, as the harness may crash due to the seeds
				}

				// Collect the seeds marked as "crash" and move them back to the source directory
				crashSeeds, err := os.ReadDir(tempDir)
				if err != nil {
					errors <- fmt.Errorf("failed to read crash seeds: %v", err)
					return
				}

				crashSeedNum := 0
				for _, seed := range crashSeeds {
					if strings.HasPrefix(seed.Name(), "crash-") {
						crashSeedNum++
						oldPath := filepath.Join(tempDir, seed.Name())
						newPath := filepath.Join(crashTargetDir, seed.Name())
						if err := moveFile(oldPath, newPath); err != nil {
							errors <- fmt.Errorf("failed to move crash seed: %v", err)
							return
						}
					}
				}

				// Move merged seeds back to source directory
				mergedSeeds, err := os.ReadDir(resultDir)
				if err != nil {
					errors <- fmt.Errorf("failed to read merged seeds: %v", err)
					return
				}

				for _, seed := range mergedSeeds {
					oldPath := filepath.Join(resultDir, seed.Name())
					newPath := filepath.Join(sourceDir, seed.Name())
					if err := moveFile(oldPath, newPath); err != nil {
						errors <- fmt.Errorf("failed to move merged seed: %v", err)
						return
					}
				}

				log.Printf("[-] Done merge batch %d: merged %d seeds to %d seeds and %d crashes\n", batchIndex, end-start, len(mergedSeeds), crashSeedNum)
			}(i)
		}

		wg.Wait()
		close(errors)

		for err := range errors {
			if err != nil {
				return err
			}
		}
	}

	// Perform one final merge to ensure all seeds are merged
	log.Printf("[+] Final merge and write to target directory\n")
	cmd := exec.Command(binary, "-timeout=1", "-merge=1", targetDir, sourceDir)
	cmd.Dir = filepath.Dir(binary)
	if output, err := cmd.CombinedOutput(); err != nil {
		log.Printf("failed to merge seeds: %v\nOutput:\n%s", err, string(output))
		// We ignore the error here, as the harness may crash due to the seeds
	}

	log.Printf("[+] Final merge from crash folder to target directory (avoid FP)\n")
	cmd = exec.Command(binary, "-timeout=1", "-merge=1", targetDir, crashTargetDir)
	cmd.Dir = filepath.Dir(binary)
	if output, err := cmd.CombinedOutput(); err != nil {
		log.Printf("failed to merge seeds: %v\nOutput:\n%s", err, string(output))
		// We ignore the error here, as the harness may crash due to the seeds
	}

	// In this stage, the crash seeds are really the crash seeds
	os.RemoveAll(crashTargetDir)
	os.MkdirAll(crashTargetDir, 0755)
	crashSeeds, err := os.ReadDir(filepath.Dir(binary))
	if err != nil {
		return fmt.Errorf("failed to read crash seeds: %v", err)
	}

	for _, seed := range crashSeeds {
		if strings.HasPrefix(seed.Name(), "crash-") {
			oldPath := filepath.Join(filepath.Dir(binary), seed.Name())
			newPath := filepath.Join(crashTargetDir, seed.Name())
			if err := moveFile(oldPath, newPath); err != nil {
				return fmt.Errorf("failed to move crash seed: %v", err)
			}
		}
	}

	finalSeeds, err := os.ReadDir(targetDir)
	if err != nil {
		return fmt.Errorf("failed to read final seeds: %v", err)
	}

	log.Printf("[-] Finish merging seeds: %d -> %d seeds in %s\n", originalSeedCount, len(finalSeeds), targetDir)

	return nil
}

func GetCoverage(ctx context.Context, req *runtime.RunRequest, lsc *locate.LocateServerComponent) (*runtime.RunResponse, error) {
	binary := "/" + req.GetHarnessBinary()
	seeds := req.GetSeedsPath()

	err_response := &runtime.RunResponse{
		Success: false,
	}

	harnessSourceFile, err := locate.LocateHarness(ctx, binary, lsc)
	if err != nil {
		log.Printf("Failed to locate harness source code: %v\n", err)
		return err_response, err
	}
	harnessSourceBase := filepath.Base(harnessSourceFile)

	tempDir, err := os.MkdirTemp("", "coverage")
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

	// The final path should be /seedgen_output/<req.GetHarnessBinary()>/merge

	finalPath := filepath.Join("/seedgen_output", req.GetHarnessBinary(), "merge")
	if err := MergeSeeds(binary, finalPath, seeds); err != nil {
		log.Printf("Failed to merge seeds: %v\n", err)
		return err_response, err
	}

	// run command: `<binary> -seed=0 -runs=0 -print_coverage=1 <tempDir>/`
	cmd := exec.Command(binary, "-seed=0", "-runs=0", "-timeout=1", "-print_coverage=1", finalPath)
	cmd.Dir = filepath.Dir(binary)
	output, _ := cmd.CombinedOutput() // ignore error, since seeds may cause the harness to crash

	// first, remember to grep the coverage from the output (use harnessSourceBase)
	coverage := string(output)
	harnessCoverage := ""
	for _, line := range strings.Split(coverage, "\n") {
		if strings.Contains(line, harnessSourceBase) {
			harnessCoverage += line + "\n"
		}
	}

	coverageReport := ""

	if harnessCoverage == "" {
		harnessCoverage = "No coverage information found."
	} else {
		// parse the harness coverage
		coverageInfos, err := parseCoverageInformation(harnessCoverage)
		if err != nil {
			log.Printf("Failed to parse coverage information: %v\n", err)
			// use the raw coverage data
			coverageReport = harnessCoverage
		} else {
			coverageSummary := generateCoverageSummary(coverageInfos)
			coverageReport, err = generateCoverageReport(harnessSourceFile, coverageInfos)

			if strings.Count(coverageReport, "\n") > 1000 {
				// if coverageReport is larger than 1000 lines, use the summary instead
				coverageReport = coverageSummary
				log.Printf("Coverage report is too large, using summary instead.")
			} else {
				// if report is not too large, we also include the summary
				coverageReport = coverageSummary + "\n" + coverageReport
			}

			if err != nil {
				log.Printf("Failed to generate coverage report: %v\n", err)
				// use the raw coverage data
				coverageReport = harnessCoverage
			}
		}
	}

	response := &runtime.RunResponse{
		Success:  true,
		Coverage: coverageReport,
	}

	return response, nil
}

type CoverageInfo struct {
	File   string
	Line   int
	Status string
	Func   string
	Hits   int
}

func parseCoverageInformation(coverageData string) ([]CoverageInfo, error) {
	var coverageInfos []CoverageInfo
	scanner := bufio.NewScanner(strings.NewReader(coverageData))

	for scanner.Scan() {
		line := scanner.Text()
		// strip the line
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "UNCOVERED_FUNC") || strings.HasPrefix(line, "COVERED_FUNC") {
			parts := strings.Split(line, " ")
			fileLine := parts[len(parts)-1]
			fileLineParts := strings.Split(fileLine, ":")
			file := fileLineParts[0]
			lineNumber := atoi(fileLineParts[1])
			status := "covered_func"
			if strings.HasPrefix(line, "UNCOVERED_FUNC") {
				status = "uncovered_func"
			}
			funcName := strings.Join(parts[5:len(parts)-1], " ")
			hits, _ := strconv.Atoi(strings.TrimPrefix(parts[2], "hits: "))
			coverageInfos = append(coverageInfos, CoverageInfo{File: file, Line: lineNumber, Status: status, Func: funcName, Hits: hits})
		} else if strings.HasPrefix(line, "UNCOVERED_PC") {
			parts := strings.Split(line, " ")
			fileLine := parts[len(parts)-1]
			fileLineParts := strings.Split(fileLine, ":")
			file := fileLineParts[0]
			lineNumber := atoi(fileLineParts[1])
			coverageInfos = append(coverageInfos, CoverageInfo{File: file, Line: lineNumber, Status: "uncovered_pc", Hits: 0})
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return coverageInfos, nil
}

func atoi(s string) int {
	var n int
	fmt.Sscanf(s, "%d", &n)
	return n
}

func generateCoverageSummary(coverageInfos []CoverageInfo) string {
	var summary strings.Builder
	summary.WriteString("List of Uncovered Functions:\n")
	summary.WriteString("================================\n")

	for _, info := range coverageInfos {
		if info.Status == "uncovered_func" {
			summary.WriteString(fmt.Sprintf("%s at line %d\n", info.Func, info.Line))
		}
	}

	summary.WriteString("\nList of Covered Branches:\n")
	summary.WriteString("================================\n")

	for _, info := range coverageInfos {
		if info.Status == "covered_func" {
			summary.WriteString(fmt.Sprintf("%s at line %d with %d hits\n", info.Func, info.Line, info.Hits))
		}
	}

	return summary.String()
}

func generateCoverageReport(sourceFile string, coverageInfos []CoverageInfo) (string, error) {
	file, err := os.Open(sourceFile)
	if err != nil {
		return "", err
	}
	defer file.Close()

	lineCoverage := make(map[int]string)
	for _, info := range coverageInfos {
		if info.File == sourceFile {
			lineCoverage[info.Line] = info.Status
		}
	}

	scanner := bufio.NewScanner(file)
	var report strings.Builder

	report.WriteString("Coverage Report:\n")
	report.WriteString("================================\n")

	lineNumber := 1
	for scanner.Scan() {
		line := scanner.Text()
		status, ok := lineCoverage[lineNumber]

		if ok {
			switch status {
			case "covered_func":
				report.WriteString(fmt.Sprintf("[COVERED]           | %4d | %s\n", lineNumber, line))
			case "uncovered_func":
				report.WriteString(fmt.Sprintf("[UNCOVERED]         | %4d | %s\n", lineNumber, line))
			case "uncovered_pc":
				report.WriteString(fmt.Sprintf("[Uncovered Branch]  | %4d | %s\n", lineNumber, line))
			}
		} else {
			report.WriteString(fmt.Sprintf("                    | %4d | %s\n", lineNumber, line))
		}
		lineNumber++
	}

	if err := scanner.Err(); err != nil {
		return "", err
	}

	return report.String(), nil
}
