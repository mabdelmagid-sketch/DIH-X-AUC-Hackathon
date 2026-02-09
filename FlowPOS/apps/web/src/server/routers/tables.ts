import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

const tableStatusSchema = z.enum(["AVAILABLE", "OCCUPIED", "RESERVED", "DIRTY"]);
const tableShapeSchema = z.enum(["RECTANGLE", "SQUARE", "CIRCLE", "OVAL"]);

const tableCreateSchema = z.object({
  locationId: z.string().uuid(),
  name: z.string().min(1, "Name is required").max(50),
  capacity: z.number().int().min(1).max(50).default(4),
  status: tableStatusSchema.default("AVAILABLE"),
  posX: z.number().int().min(0).default(0),
  posY: z.number().int().min(0).default(0),
  width: z.number().int().min(50).max(500).default(100),
  height: z.number().int().min(50).max(500).default(100),
  shape: tableShapeSchema.default("RECTANGLE"),
});

const tableUpdateSchema = tableCreateSchema.partial().omit({ locationId: true });

const tableIdSchema = z.object({
  id: z.string().uuid(),
});

export const tablesRouter = router({
  // Get all tables for a location
  list: protectedProcedure
    .input(
      z.object({
        locationId: z.string().uuid(),
        status: tableStatusSchema.optional(),
      })
    )
    .query(async ({ ctx, input }) => {
      // Verify location belongs to org
      const { data: location, error: locError } = await ctx.db
        .from("locations")
        .select("organization_id")
        .eq("id", input.locationId)
        .single();

      if (locError || location?.organization_id !== ctx.organizationId) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Location not found",
        });
      }

      let query = ctx.db
        .from("tables")
        .select("*")
        .eq("location_id", input.locationId)
        .is("deleted_at", null) // Exclude soft-deleted tables
        .order("name", { ascending: true });

      if (input.status) {
        query = query.eq("status", input.status);
      }

      const { data, error } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Get single table by ID
  getById: protectedProcedure.input(tableIdSchema).query(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("tables")
      .select("*, location:locations(*)")
      .eq("id", input.id)
      .single();

    if (error) {
      throw new TRPCError({
        code: "NOT_FOUND",
        message: "Table not found",
      });
    }

    // Verify belongs to org
    const location = data.location as { organization_id: string } | null;
    if (location?.organization_id !== ctx.organizationId) {
      throw new TRPCError({
        code: "NOT_FOUND",
        message: "Table not found",
      });
    }

    return data;
  }),

  // Get available tables for a location
  getAvailable: protectedProcedure
    .input(z.object({ locationId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("tables")
        .select("*")
        .eq("location_id", input.locationId)
        .eq("status", "AVAILABLE")
        .order("name", { ascending: true });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Create new table
  create: adminProcedure.input(tableCreateSchema).mutation(async ({ ctx, input }) => {
    // Verify location belongs to org
    const { data: location, error: locError } = await ctx.db
      .from("locations")
      .select("organization_id")
      .eq("id", input.locationId)
      .single();

    if (locError || location?.organization_id !== ctx.organizationId) {
      throw new TRPCError({
        code: "NOT_FOUND",
        message: "Location not found",
      });
    }

    const { data, error } = await ctx.db
      .from("tables")
      .insert({
        location_id: input.locationId,
        name: input.name,
        capacity: input.capacity,
        status: input.status,
        pos_x: input.posX,
        pos_y: input.posY,
        width: input.width,
        height: input.height,
        shape: input.shape,
      })
      .select()
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Update table
  update: adminProcedure
    .input(tableIdSchema.merge(tableUpdateSchema))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      const updatePayload: Record<string, unknown> = {};
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.capacity !== undefined)
        updatePayload.capacity = updateData.capacity;
      if (updateData.status !== undefined) updatePayload.status = updateData.status;
      if (updateData.posX !== undefined) updatePayload.pos_x = updateData.posX;
      if (updateData.posY !== undefined) updatePayload.pos_y = updateData.posY;
      if (updateData.width !== undefined) updatePayload.width = updateData.width;
      if (updateData.height !== undefined) updatePayload.height = updateData.height;
      if (updateData.shape !== undefined) updatePayload.shape = updateData.shape;

      const { data, error } = await ctx.db
        .from("tables")
        .update(updatePayload)
        .eq("id", id)
        .select("*, location:locations(*)")
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Soft delete table (preserves historical order references)
  delete: adminProcedure.input(tableIdSchema).mutation(async ({ ctx, input }) => {
    const { error } = await ctx.db
      .from("tables")
      .update({
        deleted_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
      .eq("id", input.id)
      .is("deleted_at", null);

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return { success: true };
  }),

  // Update table status
  updateStatus: protectedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        status: tableStatusSchema,
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("tables")
        .update({ status: input.status })
        .eq("id", input.id)
        .select()
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Bulk update table positions (for floor plan editor)
  updatePositions: adminProcedure
    .input(
      z.object({
        tables: z.array(
          z.object({
            id: z.string().uuid(),
            posX: z.number().int().min(0),
            posY: z.number().int().min(0),
            width: z.number().int().min(50).optional(),
            height: z.number().int().min(50).optional(),
          })
        ),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { error } = await (ctx.db.rpc as CallableFunction)(
        "bulk_update_table_positions",
        {
          p_tables: JSON.stringify(input.tables),
          p_organization_id: ctx.organizationId,
        }
      );

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),

  // Get table statistics for a location
  getStats: protectedProcedure
    .input(z.object({ locationId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("tables")
        .select("status, capacity")
        .eq("location_id", input.locationId);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      const tables = data ?? [];
      const total = tables.length;
      const available = tables.filter((t) => t.status === "AVAILABLE").length;
      const occupied = tables.filter((t) => t.status === "OCCUPIED").length;
      const reserved = tables.filter((t) => t.status === "RESERVED").length;
      const dirty = tables.filter((t) => t.status === "DIRTY").length;
      const totalCapacity = tables.reduce((sum, t) => sum + (t.capacity ?? 0), 0);

      return {
        total,
        available,
        occupied,
        reserved,
        dirty,
        totalCapacity,
        occupancyRate: total > 0 ? (occupied / total) * 100 : 0,
      };
    }),

  // Seat table (change from AVAILABLE or RESERVED to OCCUPIED)
  seat: protectedProcedure.input(tableIdSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("tables")
      .update({ status: "OCCUPIED" })
      .eq("id", input.id)
      .in("status", ["AVAILABLE", "RESERVED"])
      .select()
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Release table (change from OCCUPIED to DIRTY)
  release: protectedProcedure.input(tableIdSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("tables")
      .update({ status: "DIRTY" })
      .eq("id", input.id)
      .eq("status", "OCCUPIED")
      .select()
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Clean table (change from DIRTY to AVAILABLE)
  clean: protectedProcedure.input(tableIdSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("tables")
      .update({ status: "AVAILABLE" })
      .eq("id", input.id)
      .eq("status", "DIRTY")
      .select()
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Reserve table
  reserve: protectedProcedure.input(tableIdSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("tables")
      .update({ status: "RESERVED" })
      .eq("id", input.id)
      .eq("status", "AVAILABLE")
      .select()
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),
});
