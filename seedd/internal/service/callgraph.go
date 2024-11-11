package service

import (
	"BugBuster/SeedD/internal/runtime"
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	CallLogFile = "/tmp/callgraph.log"
)

type CallGraph struct {
	mutex sync.Mutex
	nodes map[string]map[string]struct{} // caller -> set of callees
}

var (
	instance *CallGraph
	once     sync.Once
)

func GetCallGraphInstance() *CallGraph {
	once.Do(func() {
		instance = &CallGraph{
			nodes: make(map[string]map[string]struct{}),
		}
	})
	return instance
}

type CallGraphService struct{}

func NewCallGraphService() *CallGraphService {
	return &CallGraphService{}
}

func (s *CallGraphService) GetCallGraph(ctx context.Context, req *runtime.GetCallGraphRequest) (*runtime.GetCallGraphResponse, error) {
	callGraph := GetCallGraphInstance()
	nodes := callGraph.Export()
	jsonData, err := json.Marshal(nodes)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to serialize call graph to JSON: %v", err)
	}
	response := &runtime.GetCallGraphResponse{
		CallGraph: string(jsonData),
	}
	return response, nil
}

// isStdFunction checks if a function name is from the standard library or other functions to exclude.
func isStdFunction(funcName string) bool {
	patterns := []string{
		"std::",
		"__gnu_cxx::",
		"operator new",
		"operator delete",
		"__cxa",
	}
	for _, pattern := range patterns {
		if strings.Contains(funcName, pattern) {
			return true
		}
	}
	return false
}

// UpdateCallGraph parses the call log and updates the call graph.
// call log is a file that contains the call graph in the following format:
// <tid>|<callee_name>|<caller_name>
func UpdateCallGraph() error {
	callGraph := GetCallGraphInstance()
	callGraph.mutex.Lock()
	defer callGraph.mutex.Unlock()

	file, err := os.Open(CallLogFile)
	if err != nil {
		return err
	}
	defer file.Close()

	type Call struct {
		ThreadID   int
		CalleeName string
		CallerName string
	}

	var calls []Call

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		// Parse the line: <tid>|<callee_name>|<caller_name>
		parts := strings.Split(line, "|")
		if len(parts) != 3 {
			continue // skip malformed lines
		}

		threadID, err := strconv.Atoi(parts[0])
		if err != nil {
			continue // skip if threadID is not an integer
		}
		calleeName := parts[1]
		callerName := parts[2]

		calls = append(calls, Call{
			ThreadID:   threadID,
			CalleeName: calleeName,
			CallerName: callerName,
		})
	}

	if err := scanner.Err(); err != nil {
		return err
	}

	callsPerThread := make(map[int][]Call)
	for _, call := range calls {
		callsPerThread[call.ThreadID] = append(callsPerThread[call.ThreadID], call)
	}

	for _, threadCalls := range callsPerThread {
		callerOf := make(map[string]string)

		for _, call := range threadCalls {
			caller := call.CallerName
			callee := call.CalleeName

			callerIsStd := isStdFunction(caller)
			calleeIsStd := isStdFunction(callee)

			if !calleeIsStd && !callerIsStd {
				// Both callee and caller are user-defined
				callGraph.addCall(caller, callee)
			} else if !callerIsStd && calleeIsStd {
				// Caller is user-defined, callee is standard
				// In this case, we log the caller for future tracking
				callerOf = make(map[string]string)
				callerOf[callee] = caller
			} else if calleeIsStd && callerIsStd {
				// Both callee and caller are standard
				// In this case, we just propagate the caller (caller of the caller)
				if parent_caller, exists := callerOf[caller]; exists {
					callerOf[callee] = parent_caller
				}
			} else if callerIsStd && !calleeIsStd {
				// Caller is standard, callee is user-defined
				// In this case, we add the parent caller to the call graph
				if parent_caller, exists := callerOf[caller]; exists {
					callGraph.addCall(parent_caller, callee)
				} else {
					fmt.Println("No parent caller found for callee:", callee)
				}
			}
		}
	}

	return nil
}

// addCall adds a caller-callee relationship to the call graph.
func (s *CallGraph) addCall(callerName, calleeName string) {
	if _, exists := s.nodes[callerName]; !exists {
		s.nodes[callerName] = make(map[string]struct{})
	}
	s.nodes[callerName][calleeName] = struct{}{}
}

// Export returns a snapshot of the call graph.
func (cg *CallGraph) Export() map[string][]string {
	cg.mutex.Lock()
	defer cg.mutex.Unlock()

	nodes := make(map[string][]string, len(cg.nodes))
	for caller, node := range cg.nodes {
		calleeNames := make([]string, 0, len(node))
		for callee := range node {
			calleeNames = append(calleeNames, callee)
		}
		nodes[caller] = calleeNames
	}
	return nodes
}
