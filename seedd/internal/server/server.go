// Package server implements the gRPC server for the SeedD service.
package server

import (
	"BugBuster/SeedD/internal/logging"
	"BugBuster/SeedD/internal/runtime"
	"context"
	"fmt"
	"net"

	"go.uber.org/zap"
	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"

	"BugBuster/SeedD/internal/service"
)

const (
	// DefaultPort is the default port for the gRPC server
	DefaultPort = 9002
	// MaxMessageSize defines the maximum message size for gRPC (1GB)
	MaxMessageSize = 1024 * 1024 * 1024
)

// Server represents the gRPC server implementation
type Server struct {
	runtime.UnimplementedSeedDServer
	runSeedsService *service.RunSeedsService
}

// NewServer creates a new instance of the Server
func NewServer() *Server {
	return &Server{
		runSeedsService: service.NewRunSeedsService(),
	}
}

// RunSeeds delegates the seed running operation to the RunSeedsService
func (s *Server) RunSeeds(ctx context.Context, req *runtime.RunSeedsRequest) (*runtime.RunSeedsResponse, error) {
	logging.Logger.Info("Running seeds",
		zap.String("harness_binary", req.HarnessBinary),
		zap.Int("seeds_count", len(req.SeedsPath)),
	)

	resp, err := s.runSeedsService.RunSeeds(ctx, req)
	if err != nil {
		logging.Logger.Error("Failed to run seeds",
			zap.String("harness_binary", req.HarnessBinary),
			zap.Error(err),
		)
		return nil, err
	}

	logging.Logger.Info("Successfully ran seeds",
		zap.String("harness_binary", req.HarnessBinary),
	)
	return resp, nil
}

// GetRegionSource retrieves the source code for a specific region
func (s *Server) GetRegionSource(ctx context.Context, req *runtime.GetRegionSourceRequest) (*runtime.GetRegionSourceResponse, error) {
	logging.Logger.Info("Getting region source",
		zap.String("filepath", req.Filepath),
		zap.Uint64("start_line", req.StartLine),
		zap.Uint64("end_line", req.EndLine),
	)

	resp, err := service.GetRegionSource(ctx, req)
	if err != nil {
		logging.Logger.Error("Failed to get region source",
			zap.String("filepath", req.Filepath),
			zap.Error(err),
		)
		return nil, err
	}

	logging.Logger.Info("Successfully retrieved region source",
		zap.String("filepath", req.Filepath),
	)
	return resp, nil
}

// GetCallGraph retrieves the call graph for the specified request
func (s *Server) GetCallGraph(ctx context.Context, req *runtime.GetCallGraphRequest) (*runtime.GetCallGraphResponse, error) {
	logging.Logger.Info("Getting call graph",
		zap.String("harness_binary", req.HarnessBinary),
	)

	resp, err := s.runSeedsService.GetCallGraph(ctx, req)
	if err != nil {
		logging.Logger.Error("Failed to get call graph",
			zap.String("harness_binary", req.HarnessBinary),
			zap.Error(err),
		)
		return nil, err
	}

	logging.Logger.Info("Successfully retrieved call graph",
		zap.String("harness_binary", req.HarnessBinary),
	)
	return resp, nil
}

// GetMergedCoverage retrieves merged coverage information
func (s *Server) GetMergedCoverage(ctx context.Context, req *runtime.GetMergedCoverageRequest) (*runtime.RunSeedsResponse, error) {
	logging.Logger.Info("Getting merged coverage",
		zap.String("harness_binary", req.HarnessBinary),
	)

	resp, err := s.runSeedsService.GetMergedCoverage(ctx, req)
	if err != nil {
		logging.Logger.Error("Failed to get merged coverage",
			zap.String("harness_binary", req.HarnessBinary),
			zap.Error(err),
		)
		return nil, err
	}

	logging.Logger.Info("Successfully retrieved merged coverage",
		zap.String("harness_binary", req.HarnessBinary),
	)
	return resp, nil
}

// GetFunctions retrieves function information
func (s *Server) GetFunctions(ctx context.Context, req *runtime.GetFunctionsRequest) (*runtime.GetFunctionsResponse, error) {
	logging.Logger.Info("Getting functions",
		zap.String("harness_binary", req.HarnessBinary),
	)

	resp, err := service.GetFunctions(ctx, req)
	if err != nil {
		logging.Logger.Error("Failed to get functions",
			zap.String("harness_binary", req.HarnessBinary),
			zap.Error(err),
		)
		return nil, err
	}

	logging.Logger.Info("Successfully retrieved functions",
		zap.String("harness_binary", req.HarnessBinary),
	)
	return resp, nil
}

// Serve starts the gRPC server with graceful shutdown support
func Serve(ctx context.Context) error {
	addr := fmt.Sprintf(":%d", DefaultPort)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen: %w", err)
	}

	opts := []grpc.ServerOption{
		grpc.MaxRecvMsgSize(MaxMessageSize),
		grpc.MaxSendMsgSize(MaxMessageSize),
	}

	grpcServer := grpc.NewServer(opts...)
	runtime.RegisterSeedDServer(grpcServer, NewServer())

	// Setup health check
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("seedd", grpc_health_v1.HealthCheckResponse_SERVING)

	// Start server
	logging.Logger.Info("Starting gRPC server",
		zap.String("address", addr),
		zap.Int("port", DefaultPort),
	)

	// Handle graceful shutdown
	go func() {
		<-ctx.Done()
		logging.Logger.Info("Shutting down gRPC server...")
		grpcServer.GracefulStop()
	}()

	if err := grpcServer.Serve(lis); err != nil {
		return fmt.Errorf("failed to serve: %w", err)
	}

	return nil
}
