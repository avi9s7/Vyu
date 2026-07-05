export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }

  static async fromResponse(response: Response) {
    const contentType = response.headers.get("content-type") ?? "";
    const detail = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    return new ApiError(
      `Vyu API request failed with status ${response.status}`,
      response.status,
      detail
    );
  }
}
