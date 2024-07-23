package locate

import (
	"bufio"
	"fmt"
	"io"
	"os/exec"
	"strconv"
	"strings"
	"sync"
)

type SymbolizerServer struct {
	process *exec.Cmd
	stdin   io.WriteCloser
	stdout  io.ReadCloser
	mutex   sync.Mutex
}

func NewSymbolizerServer(binary string) (*SymbolizerServer, error) {
	cmd := exec.Command("llvm-symbolizer", "-e", binary)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}

	if err := cmd.Start(); err != nil {
		return nil, err
	}

	return &SymbolizerServer{
		process: cmd,
		stdin:   stdin,
		stdout:  stdout,
	}, nil
}

func (s *SymbolizerServer) Symbolize(address string) (path string, lineno int, colno int, err error) {
	s.mutex.Lock()
	defer s.mutex.Unlock()

	// Create a single bufio.Scanner instance
	scanner := bufio.NewScanner(s.stdout)

	// Channel to signal when a valid line is found or an error occurs
	done := make(chan error, 1)
	go func() {
		var err error
		defer func() {
			done <- err
		}()

		for {
			if !scanner.Scan() {
				if err = scanner.Err(); err == nil {
					err = io.EOF
				}
				return
			}

			line := scanner.Text()
			// log.Printf("[+] Symbolize read line: %s\n", line)

			parts := strings.Split(line, ":")
			if len(parts) == 3 {
				var lineNumber, columnNumber int
				var parseErr error
				lineNumber, parseErr = strconv.Atoi(parts[1])
				if parseErr != nil {
					continue
				}
				columnNumber, parseErr = strconv.Atoi(parts[2])
				if parseErr != nil {
					continue
				}

				// If we reach here, the line is valid
				path = parts[0]
				lineno = lineNumber
				colno = columnNumber
				return
			}
		}
	}()

	// Send the address to the symbolizer
	if _, err = fmt.Fprintf(s.stdin, "0x%s\n", address); err != nil {
		return
	}

	// Write an invalid address to ensure termination
	if _, err = fmt.Fprintf(s.stdin, "0xffffffffffffffff\n"); err != nil {
		return
	}

	// Wait for the result or an error
	err = <-done

	// Ensure we read the invalid address response
	if err == nil {
		for scanner.Scan() {
			line := scanner.Text()
			// log.Printf("[+] Symbolize read line: %s\n", line)
			if line == "??:0:0" {
				break
			}
		}
	}
	return
}

func (s *SymbolizerServer) Close() {
	s.stdin.Close()
	s.stdout.Close()
	s.process.Wait()
}
