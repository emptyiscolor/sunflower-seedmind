package locate

import (
	"fmt"
	"log"
	"os/exec"
	"strings"
	"sync"
)

type NMCache struct {
	cache map[string]string
	mutex sync.Mutex
}

func NewNMCache() *NMCache {
	return &NMCache{
		cache: make(map[string]string),
	}
}

func (n *NMCache) getNmOutput(binary string) (string, error) {
	n.mutex.Lock()
	defer n.mutex.Unlock()

	if output, exists := n.cache[binary]; exists {
		return output, nil
	}

	nmOutput, err := exec.Command("llvm-nm", binary).CombinedOutput()
	if err != nil {
		log.Printf("Failed to run nm command: %v\n", err)
		log.Printf("Output: %s\n", nmOutput)
		return "", err
	}

	output := string(nmOutput)
	n.cache[binary] = output
	return output, nil
}

func (n *NMCache) GetFunctionAddress(binary, functionName string) (string, error) {
	nmOutput, err := n.getNmOutput(binary)
	if err != nil {
		log.Printf("Failed to get nm output: %v\n", err)
		return "", err
	}

	var functionAddress string
	for _, line := range strings.Split(nmOutput, "\n") {
		if strings.Contains(line, functionName) {
			functionAddress = strings.Fields(line)[0]
			break
		}
	}
	if functionAddress == "" {
		log.Printf("Function %s not found in the binary\n", functionName)
		log.Printf("Output: %s\n", nmOutput)
		return "", fmt.Errorf("function not found in the binary")
	}
	return functionAddress, nil
}
