package main

import (
	"bytes"
	"context"
	"log"
	"net"
	"os"
	"os/exec"
	"strings"
	"time"

	"BugBuster/SeedGenInj/internal/compile"
	"BugBuster/SeedGenInj/internal/coverage"
	"BugBuster/SeedGenInj/internal/locate"
	"BugBuster/SeedGenInj/internal/runtime"
	"BugBuster/SeedGenInj/internal/viewcode"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
)

// global server state
type server struct {
	runtime.UnimplementedSeedGenServer
	compileCmd string
	lsc        *locate.LocateServerComponent
}

func (s *server) Compile(ctx context.Context, req *runtime.CompileRequest) (*runtime.CompileResponse, error) {
	return compile.Compile(ctx, req, s.compileCmd)
}

func (s *server) Locate(ctx context.Context, req *runtime.LocateRequest) (*runtime.LocateResponse, error) {
	return locate.Locate(ctx, req, s.lsc)
}

func (s *server) View(ctx context.Context, req *runtime.ViewRequest) (*runtime.ViewResponse, error) {
	return viewcode.ViewCode(ctx, req)
}

func (s *server) Run(ctx context.Context, req *runtime.RunRequest) (*runtime.RunResponse, error) {
	return coverage.GetCoverage(ctx, req, s.lsc)
}

func (s *server) Execute(ctx context.Context, req *runtime.ExecuteRequest) (*runtime.ExecuteResponse, error) {
	command := req.GetCommand()
	ctx_timeout, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx_timeout, "/bin/sh", "-c", command)
	cmd.Env = os.Environ()

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	var returnVal int32
	err := cmd.Run()
	if err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			returnVal = int32(exitError.ExitCode())
		} else {
			// command execution failed due to some other error
			returnVal = int32(-1)
		}
	}

	return &runtime.ExecuteResponse{
		Stdout:      stdout.String(),
		Stderr:      stderr.String(),
		ReturnValue: returnVal,
	}, nil
}

func main() {
	if len(os.Args) < 2 {
		log.Fatalf("Failed to intercept build command.")
	}
	entrypoint := os.Getenv("ORIG_ENTRY")
	compileCmd := strings.Join(os.Args[1:], " ")
	compileCmd = entrypoint + " " + compileCmd

	lis, err := net.Listen("tcp", ":9002")
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	runtime.RegisterSeedGenServer(grpcServer, &server{compileCmd: compileCmd, lsc: locate.NewLocateServerComponent()})

	log.Println("[+] Seedgen-injected is running on port :9002")
	log.Println("[+] Intercepted Entrypoint: ", entrypoint)
	log.Println("[+] Intercepted Compile command: ", compileCmd)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("seedgen-injected", grpc_health_v1.HealthCheckResponse_SERVING)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
